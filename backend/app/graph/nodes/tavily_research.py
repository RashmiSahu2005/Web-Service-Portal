"""
tavily_research.py
------------------
LangGraph node: TAVILY_RESEARCH

Fallback node used when primary installation research fails max attempts.
It leverages Tavily to search for detailed installation evidence.
"""

from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.graph.state import InstallationState, InstallationResearch
from app.services.agent_event_service import AgentEventService
from app.services.tavily_service import TavilyService
from app.services.llm_service import LLMService
import json
import re

def tavily_research(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "TavilyResearchAgent"
    stage_name = "TAVILY_RESEARCH"

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")

    app_name = state.get("application_name", "Unknown")
    target_version = state.get("target_version", "latest")
    os_groups = state.get("os_groups", {})
    script_reused = state.get("script_reused", {})

    existing_strategies = {
        sig: dict(per_sig) for sig, per_sig in (state.get("strategies") or {}).items()
    }
    research_results: dict = dict(state.get("research_results") or {})
    tavily_attempted: dict = dict(state.get("tavily_attempted") or {})
    
    failure_context_map = state.get("script_failure_context") or {}

    worst_status = "RESEARCH_SUCCESS"
    error_message = None

    for sig in os_groups.keys():
        if script_reused.get(sig, False):
            continue

        tavily_attempted[sig] = True
        os_parts = sig.split("_")
        os_name = os_parts[0] if os_parts else sig
        architecture = os_parts[-1] if len(os_parts) > 1 else "unknown"

        failure_context = failure_context_map.get(sig, [])
        failure_str = ""
        if failure_context:
            failure_str = "; ".join([ctx.get("analysis", "") for ctx in failure_context[-3:]])

        broadcast_log(
            job_id, agent_name,
            f"[{sig}] Executing Tavily fallback research for {app_name}..."
        )

        try:
            evidence = TavilyService.get_detailed_installation_evidence(
                application_name=app_name,
                os_name=os_name,
                architecture=architecture,
                failure_context=failure_str
            )
            
            prompt = f"""You are an installation strategy analyst.
Your task is to determine the correct, current installation method for the following software based ONLY on the provided Tavily evidence.

APPLICATION: {app_name}
VERSION: {target_version}
OS: {os_name}
ARCHITECTURE: {architecture}

EVIDENCE FROM TAVILY:
{evidence}

Produce a JSON object conforming EXACTLY to this schema. Do not add extra fields.
If you cannot determine a value from the evidence, use null or an empty list.

{{
  "application_name": "{app_name}",
  "platform": "{os_name}",
  "architecture": "{architecture}",
  "latest_version": "string or UNKNOWN",
  "version_source_url": "string or null",
  "recommended_method": "official_deb, official_tarball, apt, etc",
  "installation_command": "string or null",
  "repository": "string or null",
  "repository_url": "string or null",
  "package_name": "string or null",
  "package_manager": "string or null",
  "verification_method": "string or null",
  "verification_command": "string or null",
  "executable_path": "string or null",
  "requires_sudo": true,
  "requires_gui": false,
  "prerequisites": ["prereq1"],
  "dependencies": ["dep1"],
  "notes": ["note1"],
  "source_urls": ["url1"],
  "confidence": 0.0,
  "research_status": "RESEARCH_SUCCESS"
}}

Return ONLY the JSON object. No explanations before or after.
"""
            raw = LLMService.generate(prompt, json_mode=True)
            clean = raw.strip()
            if clean.startswith("```json"): clean = clean[7:]
            elif clean.startswith("```"): clean = clean[3:]
            if clean.endswith("```"): clean = clean[:-3]
            clean = clean.strip()
            
            try:
                parsed = json.loads(clean)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                else:
                    raise ValueError("Failed to parse JSON")
            
            strategy = InstallationResearch.model_validate(parsed)
            strategy.research_status = "RESEARCH_SUCCESS"
            
            # Synthesize missing verification fields from the strategy
            if not strategy.verification_command and not strategy.verification_method:
                method = (strategy.recommended_method or "").lower()
                pkg = strategy.package_name or app_name.lower().replace(" ", "-")
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
                    strategy.verification_command = f"command -v {app_name.lower().replace(' ', '-')}"
                broadcast_log(
                    job_id, agent_name,
                    f"[{sig}] Synthesized verification: {strategy.verification_method} → {strategy.verification_command}"
                )
            
            strategy_dict = strategy.model_dump()
            research_results[sig] = strategy_dict

            if sig not in existing_strategies:
                existing_strategies[sig] = {}
            existing_strategies[sig][app_name] = strategy_dict

            broadcast_log(
                job_id, agent_name,
                f"[{sig}] Tavily Research produced strategy: {strategy.recommended_method}"
            )

        except Exception as exc:
            broadcast_log(job_id, agent_name, f"[{sig}] Tavily fallback failed: {exc}", "error")
            research_results[sig] = {"research_status": "RESEARCH_ERROR", "error": str(exc)}
            worst_status = "RESEARCH_ERROR"
            error_message = str(exc)

    if worst_status != "RESEARCH_SUCCESS":
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
    else:
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        
    return {
        "strategies": existing_strategies,
        "research_results": research_results,
        "tavily_attempted": tavily_attempted,
        "status": worst_status,
        "error_message": error_message,
    }
