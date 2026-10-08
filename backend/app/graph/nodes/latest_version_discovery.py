import json
import asyncio
from app.graph.state import InstallationState
from app.services.tavily_service import TavilyService
from app.services.redis_service import redis_service
from app.services.llm_service import LLMService
from app.core.logger import logger
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.version_availability_service import VersionAvailabilityService
from app.providers import ApplicationProviderRegistry
from app.utils.version_utils import (
    clean_version_string,
    compare_canonical_versions,
    is_newer_version,
    app_matches,
)


def latest_version_discovery(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "LatestVersionDiscoveryAgent"
    stage_name = "LATEST_VERSION_DISCOVERY"

    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}

    applications = state.get("applications", [])
    os_groups = state.get("os_groups", {})
    first_os = list(os_groups.keys())[0] if os_groups else "unknown_unknown"
    os_name, architecture = first_os.split("_") if "_" in first_os else (first_os, "unknown")

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")

    active_app_name = state.get("application_name")
    for app in applications:
        app_name = app.get("name") or app.get("application_name")
        if app_name != active_app_name:
            continue

        is_update = (app.get("operation") == "UPDATE")

        # ── Resolve installed version ─────────────────────────────────────────
        installed_version = app.get("canonical_installed_version") or app.get("installed_version")
        if not installed_version:
            for host_id, hvers in state.get("installed_versions", {}).items():
                if hvers.get(app_name):
                    installed_version = hvers[app_name]
                    break

        if is_update:
            if not installed_version or str(installed_version).lower() in ("null", "none", "unknown", ""):
                broadcast_log(job_id, agent_name,
                    f"[{app_name}] UPDATE BLOCKED in latest_version_discovery: installed version is unknown. "
                    "Cannot safely determine update target.", "error")
                app["status"] = "FAILED"
                app["failure_category"] = "VERSION_DETECTION_FAILED"
                app["version_check_unavailable"] = True
                continue

        target_version = app.get("version")
        is_latest = not target_version or not target_version.strip() or target_version.strip().lower() == "latest"

        # ── Handle explicit requested version ─────────────────────────────────
        if not is_latest:
            requested_ver = target_version.strip()
            app["requested_version"] = requested_ver

            broadcast_log(job_id, agent_name, f"Checking availability for explicitly requested version {requested_ver} of {app_name}")

            async def _run_availability_check():
                return await VersionAvailabilityService.check_availability(
                    requested_ver,
                    state.get("strategies", {}),
                    state.get("os_groups", {}),
                    job_id,
                    agent_name,
                    app_name=app_name
                )

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                import threading
                res_val = None
                def run_in_thread():
                    nonlocal res_val
                    res_val = asyncio.run(_run_availability_check())
                thread = threading.Thread(target=run_in_thread)
                thread.start()
                thread.join()
                availability_status = res_val
            else:
                availability_status = loop.run_until_complete(_run_availability_check())

            app["version_availability_status"] = availability_status

            if availability_status == "AVAILABLE":
                broadcast_log(job_id, agent_name, f"Requested version {requested_ver} for {app_name} is available. Skipping latest version discovery.")
                app["version_resolution_source"] = "explicit"
                app["discovered_latest_version"] = requested_ver
                app["target_version"] = requested_ver
                continue
            elif availability_status == "CHECK_NOT_APPLICABLE":
                broadcast_log(job_id, agent_name, f"Availability check is not applicable for {app_name}. Validation will occur post-download.")
                app["version_resolution_source"] = "explicit"
                app["discovered_latest_version"] = requested_ver
                app["target_version"] = requested_ver
                continue
            elif availability_status == "CHECK_FAILED":
                broadcast_log(job_id, agent_name, f"Availability check failed for {app_name} version {requested_ver}. Stopping to prevent unsafe version substitution.", "error")
                app["version_check_unavailable"] = True
                app["status"] = "FAILED"
                continue
            elif availability_status == "NOT_AVAILABLE":
                broadcast_log(job_id, agent_name, f"Requested version {requested_ver} for {app_name} is NOT available. Falling back to latest version discovery.")
                app["version_resolution_source"] = "latest_fallback"
                # Proceed to 4-tier discovery below
        else:
            app["requested_version"] = "latest" if target_version and target_version.strip().lower() == "latest" else ""
            app["version_resolution_source"] = "latest"

        # ── 4-TIER DETERMINISTIC VERSION DISCOVERY ────────────────────────────
        broadcast_log(job_id, agent_name, f"Starting authoritative version discovery for {app_name} (Installed: {installed_version or 'None'})")

        candidate_versions = []
        rejected_candidates = []
        selected_latest_version = None
        version_source = None
        source_url = None
        comparison_result = None
        decision = None

        provider = ApplicationProviderRegistry.get_provider(app_name, os_name)

        # ── Priority 1: Configured package-manager repository metadata ─────────
        authoritative_latest = None
        for host_id, host_latest in state.get("latest_versions_from_host", {}).items():
            if host_latest.get(app_name) and str(host_latest[app_name]).lower() not in ("null", "none", ""):
                authoritative_latest = host_latest[app_name]
                break
            for k, v in host_latest.items():
                if app_matches(k, app_name) and str(v).lower() not in ("null", "none", ""):
                    authoritative_latest = v
                    break
            if authoritative_latest:
                break

        if authoritative_latest:
            c1 = clean_version_string(authoritative_latest)
            if c1 and c1 not in candidate_versions:
                candidate_versions.append(c1)

            if is_update and installed_version:
                cmp_p1 = compare_canonical_versions(c1, installed_version)
                if cmp_p1 > 0:
                    selected_latest_version = c1
                    version_source = "Package Manager Repository"
                    comparison_result = f"candidate ({c1}) > installed ({installed_version})"
                    decision = "UPDATE_TARGET_FOUND"
                else:
                    if c1 not in rejected_candidates:
                        rejected_candidates.append(c1)
                    # Repository candidate is <= installed. We will also check vendor API
                    # in Priority 2 before making a final NO_UPDATE_REQUIRED determination.
            else:
                selected_latest_version = c1
                version_source = "Package Manager Repository"
                decision = "INSTALL_TARGET_FOUND"

        # ── Priority 2: Official vendor API / release feed ─────────────────────
        if not selected_latest_version:
            try:
                v_cand, v_source, v_url = provider.fetch_authoritative_vendor_version()
                if v_cand:
                    c2 = clean_version_string(v_cand)
                    if c2 and c2 not in candidate_versions:
                        candidate_versions.append(c2)

                    if is_update and installed_version:
                        cmp_p2 = compare_canonical_versions(c2, installed_version)
                        if cmp_p2 > 0:
                            selected_latest_version = c2
                            version_source = v_source
                            source_url = v_url
                            comparison_result = f"candidate ({c2}) > installed ({installed_version})"
                            decision = "UPDATE_TARGET_FOUND"
                        else:
                            if c2 not in rejected_candidates:
                                rejected_candidates.append(c2)
                            # Authoritative vendor release is <= installed
                            selected_latest_version = c2
                            version_source = v_source
                            source_url = v_url
                            comparison_result = f"authoritative latest ({c2}) <= installed ({installed_version})"
                            decision = "NO_UPDATE_REQUIRED"
                    else:
                        selected_latest_version = c2
                        version_source = v_source
                        source_url = v_url
                        decision = "INSTALL_TARGET_FOUND"
            except Exception as e:
                logger.warning(f"Error fetching vendor feed for {app_name}: {e}")

        # ── Priority 3: Official vendor release page ───────────────────────────
        if not selected_latest_version and decision != "NO_UPDATE_REQUIRED":
            try:
                page_cand, page_source, page_url = provider.fetch_vendor_release_page_version()
                if page_cand:
                    c3 = clean_version_string(page_cand)
                    if c3 and c3 not in candidate_versions:
                        candidate_versions.append(c3)

                    if is_update and installed_version:
                        cmp_p3 = compare_canonical_versions(c3, installed_version)
                        if cmp_p3 > 0:
                            selected_latest_version = c3
                            version_source = page_source
                            source_url = page_url
                            comparison_result = f"candidate ({c3}) > installed ({installed_version})"
                            decision = "UPDATE_TARGET_FOUND"
                        else:
                            if c3 not in rejected_candidates:
                                rejected_candidates.append(c3)
                            selected_latest_version = c3
                            version_source = page_source
                            source_url = page_url
                            comparison_result = f"vendor release page ({c3}) <= installed ({installed_version})"
                            decision = "NO_UPDATE_REQUIRED"
                    else:
                        selected_latest_version = c3
                        version_source = page_source
                        source_url = page_url
                        decision = "INSTALL_TARGET_FOUND"
            except Exception as e:
                logger.warning(f"Error fetching vendor release page for {app_name}: {e}")

        # ── Priority 4: Tavily as a last-resort fallback ───────────────────────
        if not selected_latest_version and decision != "NO_UPDATE_REQUIRED":
            broadcast_log(job_id, agent_name,
                f"[{app_name}] Authoritative vendor sources yielded no target. Querying Tavily as last-resort fallback...")

            installation_method = ""
            for sig, app_strategies in state.get("strategies", {}).items():
                if app_strategies.get(app_name):
                    installation_method = app_strategies[app_name].get("package_manager") or app_strategies[app_name].get("installation_method", "")
                    break

            evidence = TavilyService.get_version_evidence(
                app_name,
                current_version=installed_version or "",
                installation_method=installation_method,
                os_name=os_name,
                architecture=architecture
            )

            if evidence.startswith("Error"):
                broadcast_log(job_id, agent_name, f"[{app_name}] {evidence}", "error")
            else:
                prompt = f"""
You are a highly precise version-extraction agent. Review the following web search evidence regarding the latest STABLE, OFFICIAL release version of '{app_name}'.
Return ONLY a valid JSON object.

CRITICAL RULES:
1. NEVER invent, guess, or synthesize a version.
2. ONLY extract versions that are explicitly confirmed as currently available STABLE releases.
3. DO NOT extract prerelease, nightly, alpha, beta, rc, or future upcoming versions.
4. COMPLETELY IGNORE third-party blogs, tutorials, or news articles even if they claim a version is released.
5. ONLY trust official vendor websites, GitHub releases, or Wikipedia's "Stable release" infobox.
6. If the evidence does not clearly state a current stable release version from a TRUSTED source, return null for latest_version.

Evidence:
{evidence}

JSON format:
{{
    "latest_version": "1.2.3" or null,
    "source": "Name of the source",
    "source_url": "URL of the source",
    "confidence": 0.0 to 1.0 (use < 0.6 if uncertain)
}}
"""
                try:
                    llm_res = LLMService.generate(prompt, json_mode=True)
                    clean_res = llm_res.strip()
                    if clean_res.startswith("```json"): clean_res = clean_res[7:]
                    if clean_res.startswith("```"): clean_res = clean_res[3:]
                    if clean_res.endswith("```"): clean_res = clean_res[:-3]
                    clean_res = clean_res.strip()

                    parsed = json.loads(clean_res)
                    if parsed.get("latest_version") and parsed.get("confidence", 0) > 0.6:
                        raw_c4 = parsed["latest_version"]
                        c4 = clean_version_string(raw_c4)
                        if c4 and c4 not in candidate_versions:
                            candidate_versions.append(c4)

                        if is_update and installed_version:
                            cmp_p4 = compare_canonical_versions(c4, installed_version)
                            if cmp_p4 > 0:
                                selected_latest_version = c4
                                version_source = "Tavily Web Search"
                                source_url = parsed.get("source_url")
                                comparison_result = f"candidate ({c4}) > installed ({installed_version})"
                                decision = "UPDATE_TARGET_FOUND"
                            else:
                                if c4 not in rejected_candidates:
                                    rejected_candidates.append(c4)
                                comparison_result = f"Tavily candidate ({c4}) <= installed ({installed_version}) - REJECTED (stale web result)"
                                # Never allow a stale Tavily result to become target version or NO_UPDATE_REQUIRED!
                        else:
                            selected_latest_version = c4
                            version_source = "Tavily Web Search"
                            source_url = parsed.get("source_url")
                            decision = "INSTALL_TARGET_FOUND"
                except Exception as e:
                    logger.error(f"[{app_name}] LLM Tavily extraction failed: {e}")

        # ── Final Update Evaluation & Guardrails ───────────────────────────────
        if is_update:
            if decision == "NO_UPDATE_REQUIRED":
                app["discovered_latest_version"] = selected_latest_version or installed_version
                app["target_version"] = selected_latest_version or installed_version
                app["is_up_to_date"] = True
                app["version_source"] = version_source or "Authoritative Vendor Source"
            elif decision == "UPDATE_TARGET_FOUND" and selected_latest_version:
                app["discovered_latest_version"] = selected_latest_version
                app["target_version"] = selected_latest_version
                app["version_source"] = version_source
                app["is_up_to_date"] = False
                redis_service.set_latest_version(app_name, os_name, architecture, {
                    "latest_version": selected_latest_version,
                    "source": version_source,
                    "source_url": source_url
                })
            else:
                # Neither valid newer version nor authoritative NO_UPDATE_REQUIRED was found
                decision = "VERSION_DISCOVERY_FAILED"
                app["status"] = "FAILED"
                app["failure_category"] = "VERSION_DISCOVERY_FAILED"
                app["error_message"] = f"Could not establish a trustworthy newer version than installed ({installed_version})."
                app["version_check_unavailable"] = True

                try:
                    from app.services.email_service import EmailService
                    requester_email = state.get("requester_email")
                    if requester_email:
                        email_msg = state.get("email_message", {})
                        first_host = state.get("hostname") or (state.get("host_ids")[0] if state.get("host_ids") else "Unknown")
                        EmailService.send_version_discovery_failed_email(
                            recipient_email=requester_email,
                            application_name=app_name,
                            hostname=str(first_host),
                            installed_version=installed_version,
                            reason=app["error_message"],
                            in_reply_to=msg_id
                        )
                except Exception as e:
                    logger.warning(f"Failed to send version discovery failed email: {e}")
        else:
            # INSTALL flow
            if selected_latest_version:
                app["discovered_latest_version"] = selected_latest_version
                app["target_version"] = selected_latest_version
                app["version_source"] = version_source
                redis_service.set_latest_version(app_name, os_name, architecture, {
                    "latest_version": selected_latest_version,
                    "source": version_source,
                    "source_url": source_url
                })
            else:
                req_version = app.get("version") or app.get("requested_version") or "Latest"
                app["discovered_latest_version"] = req_version
                app["target_version"] = req_version
                app["version_source"] = "Requested Version / Package Manager"
                decision = "INSTALL_TARGET_FOUND"

        # ── REQUIRED STRUCTURED LOGGING ─────────────────────────────────────────
        broadcast_log(job_id, agent_name,
            f"[{app_name}] Version Discovery Decision Summary:\n"
            f"  installed_version: {installed_version or 'None'}\n"
            f"  version_source: {version_source or 'None'}\n"
            f"  candidate_versions: {candidate_versions}\n"
            f"  rejected_candidates: {rejected_candidates}\n"
            f"  selected_latest_version: {selected_latest_version or 'None'}\n"
            f"  comparison_result: {comparison_result or 'None'}\n"
            f"  decision: {decision}"
        )

    failed_apps = [a for a in applications if a.get("status") == "FAILED"]
    ret_dict = {"applications": applications}
    if len(failed_apps) == len(applications) and len(applications) > 0:
        ret_dict["status"] = "FAILED"

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return ret_dict
