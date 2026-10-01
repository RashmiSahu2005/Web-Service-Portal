import json
import asyncio
from app.graph.state import InstallationState
from app.services.tavily_service import TavilyService
from app.services.redis_service import redis_service
from app.services.llm_service import LLMService
from app.core.logger import logger
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.version_availability_service import VersionAvailabilityService

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
            
        target_version = app.get("version")
        
        is_latest = not target_version or not target_version.strip() or target_version.strip().lower() == "latest"
        
        if is_latest:
            app["requested_version"] = "latest" if target_version and target_version.strip().lower() == "latest" else ""
            app["version_resolution_source"] = "latest"
        else:
            requested_ver = target_version.strip()
            app["requested_version"] = requested_ver
            
            broadcast_log(job_id, agent_name, f"Checking availability for explicitly requested version {requested_ver} of {app_name}")
            
            # Call availability service synchronously using an event loop
            async def _run_availability_check():
                return await VersionAvailabilityService.check_availability(
                    requested_ver,
                    state.get("strategies", {}),
                    state.get("os_groups", {}),
                    job_id,
                    agent_name
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
                broadcast_log(job_id, agent_name, f"Requested version {requested_ver} for {app_name} is available. Skipping Tavily discovery.")
                app["version_resolution_source"] = "explicit"
                app["discovered_latest_version"] = None # Not needed
                continue
                
            elif availability_status == "CHECK_NOT_APPLICABLE":
                broadcast_log(job_id, agent_name, f"Availability check is not applicable for {app_name}. Validation will occur post-download.")
                app["version_resolution_source"] = "explicit"
                app["discovered_latest_version"] = None # Not needed
                continue
                
            elif availability_status == "CHECK_FAILED":
                broadcast_log(job_id, agent_name, f"Availability check failed for {app_name} version {requested_ver}. Stopping to prevent unsafe version substitution.", "error")
                app["version_check_unavailable"] = True
                app["status"] = "FAILED"
                continue
                
            elif availability_status == "NOT_AVAILABLE":
                broadcast_log(job_id, agent_name, f"Requested version {requested_ver} for {app_name} is NOT available. Falling back to latest version discovery.")
                app["version_resolution_source"] = "latest_fallback"
                # Fall through to FastMCP/Tavily

        if app.get("status") == "FAILED":
            continue

        broadcast_log(job_id, agent_name, f"Starting latest version discovery for {app_name}")
        
        discovered_version = None
        version_check_unavailable = False
        
        cached_data = redis_service.get_latest_version(app_name, os_name, architecture)
        
        # Get authoritative latest if available
        authoritative_latest = None
        for host_id, host_latest in state.get("latest_versions_from_host", {}).items():
            if host_latest.get(app_name) and host_latest[app_name] != "null":
                authoritative_latest = host_latest[app_name]
                break

        if cached_data and cached_data.get("latest_version"):
            discovered_version = cached_data["latest_version"]
            if authoritative_latest:
                if discovered_version != authoritative_latest:
                    broadcast_log(job_id, agent_name, f"[{app_name}] Cached candidate {discovered_version} differs from authoritative {authoritative_latest}. Overriding cache.", "warning")
                    discovered_version = authoritative_latest
                    redis_service.set_latest_version(app_name, os_name, architecture, {"latest_version": discovered_version, "source": "Package Manager"})
                else:
                    broadcast_log(job_id, agent_name, f"[{app_name}] Using cached latest version: {discovered_version} (Validated against package manager)")
            else:
                broadcast_log(job_id, agent_name, f"[{app_name}] Using cached latest version: {discovered_version} (Source: {cached_data.get('source')})")
        elif authoritative_latest:
            discovered_version = authoritative_latest
            broadcast_log(job_id, agent_name, f"[{app_name}] Using authoritative version {discovered_version} directly from package manager. Skipping Tavily.")
            redis_service.set_latest_version(app_name, os_name, architecture, {"latest_version": discovered_version, "source": "Package Manager"})
        else:
            broadcast_log(job_id, agent_name, f"[{app_name}] Cache missed and no authoritative package manager version available. Querying Tavily MCP for live web evidence...")
            
            # Find the current version (from the first host that has it)
            current_version = ""
            for host_id, host_versions in state.get("installed_versions", {}).items():
                if host_versions.get(app_name):
                    current_version = host_versions[app_name]
                    break
                    
            # Find the installation method (from the first OS group that has it)
            installation_method = ""
            for sig, app_strategies in state.get("strategies", {}).items():
                if app_strategies.get(app_name):
                    installation_method = app_strategies[app_name].get("package_manager") or app_strategies[app_name].get("installation_method", "")
                    break
                    
            evidence = TavilyService.get_version_evidence(app_name, current_version=current_version, installation_method=installation_method, os_name=os_name, architecture=architecture)
            
            if evidence.startswith("Error"):
                broadcast_log(job_id, agent_name, f"[{app_name}] {evidence}", "error")
                version_check_unavailable = True
            else:
                broadcast_log(job_id, agent_name, f"[{app_name}] Analyzing web evidence with LLM...")
                prompt = f"""
                You are a highly precise version-extraction agent. Review the following web search evidence regarding the latest STABLE, OFFICIAL release version of '{app_name}'.
                Return ONLY a valid JSON object.
                
                CRITICAL RULES:
                1. NEVER invent, guess, or synthesize a version.
                2. ONLY extract versions that are explicitly confirmed as currently available STABLE releases.
                3. DO NOT extract prerelease, nightly, alpha, beta, rc, or future upcoming versions.
                4. COMPLETELY IGNORE third-party blogs, tutorials, or news articles (e.g., qainsights, medium) even if they claim a version is released.
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
                    
                    # Sanitize the output to remove markdown blocks if any
                    clean_res = llm_res.strip()
                    if clean_res.startswith("```json"):
                        clean_res = clean_res[7:]
                    if clean_res.startswith("```"):
                        clean_res = clean_res[3:]
                    if clean_res.endswith("```"):
                        clean_res = clean_res[:-3]
                    clean_res = clean_res.strip()
                    
                    if not clean_res:
                        raise ValueError("LLM returned an empty response")
                        
                    parsed = json.loads(clean_res)
                    
                    if parsed.get("latest_version") and parsed.get("confidence", 0) > 0.6:
                        candidate_version = parsed["latest_version"]
                        broadcast_log(job_id, agent_name, f"[{app_name}] LLM Candidate version from web: {candidate_version} from {parsed.get('source_url')}")
                        
                        # Validate against authoritative source if available
                        authoritative_latest = None
                        for host_id, host_latest in state.get("latest_versions_from_host", {}).items():
                            if host_latest.get(app_name) and host_latest[app_name] != "null":
                                authoritative_latest = host_latest[app_name]
                                break
                                
                        if authoritative_latest:
                            if candidate_version != authoritative_latest:
                                broadcast_log(job_id, agent_name, f"[{app_name}] Candidate {candidate_version} differs from authoritative package manager {authoritative_latest}. Using authoritative.", "warning")
                            else:
                                broadcast_log(job_id, agent_name, f"[{app_name}] Candidate {candidate_version} validated against authoritative source.")
                            discovered_version = authoritative_latest
                            parsed["latest_version"] = discovered_version
                            parsed["source"] = "Package Manager"
                        else:
                            # Verify candidate version against current installed version to prevent stale web downgrades
                            def _to_tuple(v):
                                if not v: return ()
                                import re
                                return tuple(int(x) for x in re.findall(r'\d+', str(v).lstrip('vV')))
                                
                            cand_tup = _to_tuple(candidate_version)
                            curr_tup = _to_tuple(current_version)
                            
                            if current_version and cand_tup and curr_tup and cand_tup < curr_tup:
                                broadcast_log(job_id, agent_name, f"[{app_name}] Candidate version {candidate_version} from web is lower than installed version {current_version}. Rejecting stale web result.", "warning")
                                discovered_version = None
                                version_check_unavailable = True
                            else:
                                discovered_version = candidate_version
                                redis_service.set_latest_version(app_name, os_name, architecture, parsed)
                    else:
                        broadcast_log(job_id, agent_name, f"[{app_name}] LLM could not confidently determine the latest version from evidence.", "warning")
                        # Fallback to authoritative source if LLM failed
                        if authoritative_latest:
                            discovered_version = authoritative_latest
                            broadcast_log(job_id, agent_name, f"[{app_name}] Using authoritative version {discovered_version} as fallback.")
                            redis_service.set_latest_version(app_name, os_name, architecture, {"latest_version": discovered_version, "source": "Package Manager"})
                        else:
                            version_check_unavailable = True
                        
                except Exception as e:
                    logger.error(f"[{app_name}] LLM parsing failed: {e}")
                    broadcast_log(job_id, agent_name, f"[{app_name}] Failed to parse LLM version discovery response. No safe fallback available.", "error")
                    version_check_unavailable = True

        app["discovered_latest_version"] = discovered_version
        app["version_check_unavailable"] = version_check_unavailable

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    
    return {"applications": applications}
