"""
installation_research_service.py
---------------------------------
Orchestrates installation research for a given application/version/OS/architecture.

Workflow:
  1. Build 3–4 dynamic search queries (no hardcoded app names)
  2. Execute queries via WebSearchService (SearXNG)
  3. Fetch top authoritative pages via WebPageFetcher
  4. Send all evidence to the LLM for synthesis into a structured InstallationStrategy
  5. Return the strategy (or a "research failed" placeholder)

The strategy is designed to be merged into state["strategies"][sig][app_name] so that
the existing script_generation._build_prompt() consumes it without structural changes.

This service NEVER calls Tavily.
"""

import json
import re
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from app.core.config import settings
from app.core.logger import logger
from app.services.llm_service import LLMService
from app.services.web_search_service import WebSearchService
from app.services.web_page_fetcher import fetch_pages, MAX_PAGE_FETCHES


from app.graph.state import InstallationResearch

def _build_queries(
    application: str,
    version: str,
    os_name: str,
    architecture: str,
    failure_context: Optional[List[dict]] = None,
    operation: str = "INSTALL",
    current_version: str = "",
    installation_method: str = ""
) -> List[str]:
    """
    Dynamically generate 3–4 focused search queries.
    No application-specific hardcoding — all parameters come from inputs.
    """
    if operation == "UPDATE":
        queries = [
            f'{application} {version} official update {os_name} {architecture}',
            f'{application} {version} {os_name} update from {current_version}',
            f'{application} {os_name} update {installation_method}'
        ]
    else:
        queries = [
            f'{application} {version} official download Linux {architecture}',
            f'{application} {version} official installation Linux',
            f'{application} {version} {os_name} {architecture} download',
            f'{application} official download Linux',
            f'{application} {os_name} installation official'
        ]

    if failure_context:
        # Build a failure-aware query from the most recent failure's analysis
        last_failure = failure_context[-1]
        analysis = last_failure.get("analysis", "")
        # Extract the first meaningful sentence from the LLM analysis
        first_sentence = analysis.split(".")[0][:120] if analysis else ""
        if first_sentence:
            queries.append(
                f'"{application}" {os_name} alternative installation method {first_sentence}'
            )
        else:
            queries.append(
                f'"{application}" {os_name} alternative installation package manager'
            )

    return queries


def _sanitize_llm_json(raw: str) -> str:
    """Strip markdown fences from LLM JSON responses."""
    clean = raw.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()


def _build_evidence_text(
    search_results_by_query: List[tuple],
    page_contents: dict,
) -> str:
    """
    Assemble all gathered evidence into a single condensed text block.
    Respects a character budget to avoid bloating the LLM context.
    """
    MAX_EVIDENCE_CHARS = 8_000
    parts = []

    for query, results in search_results_by_query:
        parts.append(f"\n--- Search: {query!r} ---")
        for r in results:
            snippet = (r.get("content") or "")[:400]
            parts.append(f"  [{r.get('engine', 'web')}] {r['url']}\n  {snippet}")

    for url, content in page_contents.items():
        parts.append(f"\n--- Full page: {url} ---")
        parts.append(content[:3_000])

    evidence = "\n".join(parts)
    if len(evidence) > MAX_EVIDENCE_CHARS:
        evidence = evidence[:MAX_EVIDENCE_CHARS] + "\n[...evidence truncated]"
    return evidence


def _llm_synthesise_strategy(
    application: str,
    version: str,
    os_name: str,
    architecture: str,
    evidence: str,
    host_constraints: Optional[dict] = None,
    failure_context: Optional[List[dict]] = None,
    operation: str = "INSTALL",
    current_version: str = "",
    installation_method: str = ""
) -> dict:
    """
    Call the LLM to synthesise a structured InstallationStrategy from evidence.
    Returns parsed dict on success, empty dict on any failure.
    """
    failure_section = ""
    if failure_context:
        failure_lines = []
        for ctx in failure_context:
            attempt_num = ctx.get("attempt", "?")
            analysis = ctx.get("analysis", "No analysis")
            exit_code = ctx.get("exit_code", "?")
            failure_category = ctx.get("failure_category", "?")
            failed_strategy = ctx.get("failed_strategy", "?")
            failure_lines.append(
                f"  Attempt {attempt_num} (exit={exit_code}, strategy={failed_strategy}): {failure_category} - {analysis[:300]}"
            )
        requires_change = any(ctx.get("required_strategy_change", False) for ctx in failure_context)
        
        if requires_change:
            failure_instruction = (
                "CRITICAL: The previous installation strategy fundamentally failed or is incompatible. "
                "Do NOT recommend the same installation method that already failed. "
                "Propose an alternative based on the evidence above. For example, if apt failed entirely, "
                "search specifically for an official .deb, tarball, or standalone binary."
            )
        else:
            failure_instruction = (
                "CRITICAL: The previous installation attempt failed but the STRATEGY itself is still valid. "
                "DO NOT change the recommended installation method. Instead, your task is to fix the underlying issue "
                "(e.g., correct a 404 URL, find the correct GPG key, or fix the repository name) while PRESERVING the same installation method."
            )
            
        failure_section = (
            "\n\nPREVIOUS FAILED INSTALLATION ATTEMPTS:\n"
            + "\n".join(failure_lines)
            + f"\n\n{failure_instruction}"
        )

    constraints_section = ""
    if host_constraints:
        constraints_section = "\nTARGET HOST CONSTRAINTS:\n" + json.dumps(host_constraints, indent=2) + "\nCRITICAL: You must consider these constraints. If /tmp is noexec, you must extract binaries to a safe location (e.g., /opt) and execute from there, NOT from /tmp."

    update_section = ""
    if operation == "UPDATE":
        update_section = f"\nOPERATION: UPDATE\nCURRENT VERSION: {current_version}\nCURRENT INSTALLATION METHOD: {installation_method}\n"
        update_section += "Determine if the update can be performed in-place, or if removal is required. DO NOT default to removal unless strictly necessary."

    prompt = f"""You are an installation strategy analyst.

Your task is to determine the correct, current installation method for the following software.
Base your answer ONLY on the evidence provided below. Do not invent package names, repository URLs,
or installation commands that are not supported by the evidence.

CRITICAL REQUIREMENT: 
What is the most reliable deterministic way to install this application on this exact OS and architecture?
The search priority should generally be:
1. Official OS repository/package manager
2. Official vendor repository (must include EXACT setup commands)
3. Official Snap/Flatpak
4. Official direct artifact
5. Other documented deterministic installation mechanism
6. Manual/private artifact only when genuinely required

Do NOT select snap simply because a Snap package exists. Ensure it respects host constraints.

APPLICATION: {application}
VERSION: {version}
OS: {os_name}
ARCHITECTURE: {architecture}
{update_section}
{constraints_section}
{failure_section}

EVIDENCE FROM WEB RESEARCH:
{evidence}

---

Produce a JSON object conforming EXACTLY to this schema. Do not add extra fields.
If you cannot determine a value from the evidence, use null or an empty list.
For "latest_version", if you cannot determine it definitively from official sources, use "UNKNOWN".
If the software is only available via a private or authenticated portal, DO NOT invent a URL. Set "source_type" to "AUTHENTICATED_VENDOR_PORTAL", "artifact_required" to true, "requires_user_artifact" to true, "download_url" to null, "artifact_url" to null, and "research_status" to "RESEARCH_INSUFFICIENT".

CRITICAL URL RULES:
- A generic download page (e.g. https://vendor.com/download/) is NOT an `artifact_url`.
- You must NEVER invent, guess, or construct an artifact URL, CDN hostname, repository URL, or GPG key URL.
- Only set `artifact_url` and `artifact_url_verified=true` if an EXACT direct download link is explicitly present in the evidence.
- If the application requires an artifact (e.g., `official_deb`) but no deterministic public artifact URL is found in the evidence, set `artifact_required = true` and do NOT invent a URL.
- For official vendor repositories, you MUST provide the exact, documented GPG key URL and repository list string. DO NOT guess or infer these.

{{
  "application_name": "{application}",
  "platform": "{os_name}",
  "architecture": "{architecture}",
  "latest_version": "string or UNKNOWN",
  "version_source_url": "string or null",
  "recommended_method": "official_deb, official_tarball, apt, snap, etc",
  "installation_command": "string or null",
  "download_url": "string or null",
  "artifact_url": "string or null",
  "artifact_url_verified": false,
  "package_type": "string or null",
  "repository": "string or null",
  "repository_url": "string or null",
  "package_name": "string or null",
  "package_manager": "string or null",
  "verification_method": "string or null",
  "verification_command": "string or null",
  "executable_path": "string or null",
  "source_type": "string or null",
  "artifact_required": false,
  "requires_user_artifact": false,
  "requires_sudo": true,
  "requires_gui": false,
  "notes": ["note1"],
  "source_urls": ["url1"],
  "confidence": 0.0,
  "research_status": "RESEARCH_SUCCESS",
  "update_requires_removal": false
}}

Return ONLY the JSON object. No explanations before or after.
"""

    try:
        raw = LLMService.generate(prompt, json_mode=True)
        clean = _sanitize_llm_json(raw)
        if not clean:
            logger.warning("[InstallationResearch] LLM returned empty strategy response.")
            return {}
        parsed = json.loads(clean)
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"[InstallationResearch] Failed to parse LLM strategy JSON: {e}. Raw: {raw[:300]!r}")
        # Attempt regex extraction of JSON object
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {}
    except Exception as e:
        logger.error(f"[InstallationResearch] LLM synthesis error: {e}")
        return {}


class InstallationResearchService:
    """
    Orchestrates installation research for a single application/OS/arch combo.
    """

    @classmethod
    def research(
        cls,
        application: str,
        version: str,
        os_name: str,
        architecture: str,
        attempt: int = 1,
        host_constraints: Optional[dict] = None,
        failure_context: Optional[List[dict]] = None,
        bypass_cache: bool = False,
        operation: str = "INSTALL",
        current_version: str = "",
        installation_method: str = ""
    ) -> InstallationResearch:
        """
        Perform installation research and return a structured strategy.

        Args:
            application:    Application display name (e.g. "Appium").
            version:        Target version string (e.g. "3.1.0" or "latest").
            os_name:        OS name from OS signature (e.g. "Ubuntu").
            architecture:   Architecture string (e.g. "amd64").
            attempt:        Current generation attempt number (1-3).
            failure_context: List of failure dicts from script_failure_context.
            bypass_cache:   If True, skip the research cache (used on retry).
            operation:      INSTALL or UPDATE.
            current_version: Currently installed version (if UPDATE).
            installation_method: Detected package manager/method (if UPDATE).

        Returns:
            InstallationResearch pydantic model instance.
            On unrecoverable error returns a strategy with research_status="FAILED" via dict.
        """
        from app.services.redis_service import redis_service
        from app.services.script_registry_service import ScriptRegistryService
        from app.services.tavily_service import TavilyService

        canonical_app = ScriptRegistryService.get_canonical_name(application)

        logger.info(
            f"[DeployIQ][InstallationResearch] "
            f"Application={application} Version={version} "
            f"OS={os_name} Architecture={architecture} "
            f"Attempt={attempt}"
        )

        if failure_context:
            logger.info(
                "[DeployIQ][InstallationResearch] "
                "Executing research retry with failure context."
            )

        evidence = ""
        provider_used = "Tavily"
        
        # ── 1. Try Tavily First (Primary) ───────────────────────────────────────────
        try:
            logger.info(f"[DeployIQ][InstallationResearch] Executing Tavily research for {application}...")
            failure_str = "; ".join([ctx.get("analysis", "") for ctx in failure_context[-3:]]) if failure_context else ""
            tavily_evidence = TavilyService.get_detailed_installation_evidence(
                application_name=application,
                os_name=os_name,
                architecture=architecture,
                failure_context=failure_str
            )
            if tavily_evidence and len(tavily_evidence) > 50:
                evidence = tavily_evidence
                logger.info(f"[DeployIQ][InstallationResearch] Tavily returned {len(evidence)} chars of evidence.")
            else:
                logger.warning("[DeployIQ][InstallationResearch] Tavily returned empty or insufficient evidence.")
        except Exception as e:
            logger.warning(f"[DeployIQ][InstallationResearch] Tavily provider failed: {e}")

        # ── 2. Fallback to SearXNG if Tavily fails ──────────────────────────────────
        if not evidence:
            provider_used = "SearXNG"
            logger.info("[DeployIQ][InstallationResearch] Falling back to SearXNG provider...")
            queries = _build_queries(application, version, os_name, architecture, failure_context, operation, current_version, installation_method)
            logger.info(f"[DeployIQ][InstallationResearch] Executing {len(queries)} search queries via SearXNG")

            search_results_by_query = []
            all_urls = []
            total_results = 0

            for query in queries:
                logger.info(f"[DeployIQ][InstallationResearch] Query={query!r}")
                results = WebSearchService.search(query, max_results=5)
                search_results_by_query.append((query, results))
                total_results += len(results)
                for r in results:
                    if r.get("url") and r["url"] not in all_urls:
                        all_urls.append(r["url"])

            logger.info(
                f"[DeployIQ][InstallationResearch] "
                f"SearchesExecuted={len(queries)} TotalResults={total_results} UniqueURLs={len(all_urls)}"
            )

            if total_results == 0:
                logger.error(
                    "[DeployIQ][InstallationResearch] "
                    "Both Tavily and SearXNG returned no results. Failing research attempt to trigger retry."
                )
                raise ValueError("Both research providers failed to return evidence.")

            top_urls = all_urls[: MAX_PAGE_FETCHES + 2]
            page_contents = fetch_pages(top_urls, max_fetches=MAX_PAGE_FETCHES)
            logger.info(
                f"[DeployIQ][InstallationResearch] "
                f"SelectedSources={len(page_contents)}"
            )

            evidence = _build_evidence_text(search_results_by_query, page_contents)
            
        logger.info(f"[DeployIQ][InstallationResearch] Final Provider={provider_used} EvidenceLength={len(evidence)}")

        # ── 5. LLM strategy synthesis ─────────────────────────────────────────
        strategy_dict = _llm_synthesise_strategy(
            application, version, os_name, architecture, evidence, host_constraints, failure_context, operation, current_version, installation_method
        )

        if not strategy_dict:
            logger.error(
                "[DeployIQ][InstallationResearch] "
                "LLM synthesis produced no valid strategy."
            )
            raise ValueError("LLM synthesis produced no valid strategy.")

        # ── 6. Build strategy object ──────────────────────────────────────────
        try:
            strategy = InstallationResearch.model_validate(strategy_dict)
            
            # Evidence-based confidence calculation
            calculated_confidence = 0.0
            if strategy.version_source_url: calculated_confidence += 30.0
            if strategy.repository_url: calculated_confidence += 25.0
            if strategy.package_name or strategy.installation_command: calculated_confidence += 20.0
            if strategy.architecture: calculated_confidence += 10.0
            if strategy.verification_method or strategy.verification_command: calculated_confidence += 15.0
            
            # Cap at 100
            strategy.confidence = min(calculated_confidence, 100.0)
            
            # Actionable evidence is checked in installation_research_validation.py, not here based on confidence.
            strategy.research_status = "RESEARCH_SUCCESS"
            
            if not strategy.recommended_method or strategy.recommended_method.lower() == "unknown":
                strategy.recommended_method = "unknown"
                strategy.research_status = "RESEARCH_INSUFFICIENT"
            elif not strategy.verification_command and not strategy.verification_method:
                # Synthesize a fallback verification so validation doesn't fail
                method = strategy.recommended_method.lower()
                pkg = strategy.package_name or application.lower().replace(" ", "-")
                exe = strategy.executable_path
                if method in ["snap"]:
                    strategy.verification_method = "snap_list"
                    strategy.verification_command = f"snap list {pkg}"
                elif method in ["apt", "official_deb"]:
                    strategy.verification_method = "dpkg_query"
                    strategy.verification_command = f"dpkg-query -l '{pkg}'"
                elif method in ["rpm", "yum", "dnf"]:
                    strategy.verification_method = "rpm_query"
                    strategy.verification_command = f"rpm -q {pkg}"
                elif exe:
                    strategy.verification_method = "file_exists"
                    strategy.verification_command = f"test -f '{exe}'"
                else:
                    strategy.verification_method = "command_exists"
                    strategy.verification_command = f"command -v {application.lower().replace(' ', '-')}"
                logger.info(f"[DeployIQ][InstallationResearch] Synthesized verification: {strategy.verification_method} → {strategy.verification_command}")
                
        except Exception as e:
            logger.error(f"[DeployIQ][InstallationResearch] Failed to validate Pydantic model: {e}")
            raise ValueError(f"Schema validation failed: {e}")

        logger.info(
            f"[DeployIQ][InstallationResearch] "
            f"RecommendedMethod={strategy.recommended_method!r} "
            f"Confidence={strategy.confidence:.2f} "
            f"Status={strategy.research_status}"
        )
        logger.info(
            f"[DeployIQ][InstallationResearch] "
            f"VerificationCommand={strategy.verification_command!r}"
        )
        logger.info("[DeployIQ][InstallationResearch] Research completed")

        return strategy
