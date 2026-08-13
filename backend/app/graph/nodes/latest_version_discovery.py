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
        
    app_name = state.get("application_name", "")
    target_version = state.get("version")
    
    is_latest = not target_version or not target_version.strip() or target_version.strip().lower() == "latest"
    
    updates = {}
    
    if is_latest:
        updates["requested_version"] = "latest" if target_version and target_version.strip().lower() == "latest" else ""
        updates["version_resolution_source"] = "latest"
    else:
        requested_ver = target_version.strip()
        updates["requested_version"] = requested_ver
        
        broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
        broadcast_log(job_id, agent_name, f"Checking availability for explicitly requested version {requested_ver}")
        
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
            
        updates["version_availability_status"] = availability_status
        
        if availability_status == "AVAILABLE":
            broadcast_log(job_id, agent_name, f"Requested version {requested_ver} is available. Skipping Tavily discovery.")
            updates["version_resolution_source"] = "explicit"
            updates["discovered_latest_version"] = None # Not needed
            broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
            return updates
            
        elif availability_status == "CHECK_FAILED":
            broadcast_log(job_id, agent_name, f"Availability check failed for {requested_ver}. Stopping to prevent unsafe version substitution.", "error")
            updates["version_check_unavailable"] = True
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return updates
            
        elif availability_status == "NOT_AVAILABLE":
            broadcast_log(job_id, agent_name, f"Requested version {requested_ver} is NOT available. Falling back to latest version discovery.")
            updates["version_resolution_source"] = "latest_fallback"
            # Fall through to FastMCP/Tavily

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, f"Starting latest version discovery for {app_name}")
    
    discovered_version = None
    version_check_unavailable = False
    
    os_groups = state.get("os_groups", {})
    first_os = list(os_groups.keys())[0] if os_groups else "unknown_unknown"
    os_name, architecture = first_os.split("_") if "_" in first_os else (first_os, "unknown")
    
    cached_data = redis_service.get_latest_version(app_name, os_name, architecture)
    if cached_data and cached_data.get("latest_version"):
        discovered_version = cached_data["latest_version"]
        broadcast_log(job_id, agent_name, f"Using cached latest version: {discovered_version} (Source: {cached_data.get('source')})")
    else:
        broadcast_log(job_id, agent_name, "Cache missed or expired. Querying Tavily MCP for live web evidence...")
        evidence = TavilyService.get_version_evidence(app_name)
        
        if evidence.startswith("Error"):
            broadcast_log(job_id, agent_name, evidence, "error")
            version_check_unavailable = True
        else:
            broadcast_log(job_id, agent_name, "Analyzing web evidence with LLM...")
            prompt = f"""
            You are a version-extraction agent. Review the following web search evidence regarding the latest official release version of '{app_name}'.
            Return ONLY a valid JSON object. Do not invent a version if the evidence does not clearly state one.
            Prioritize official vendor websites, GitHub releases, or trusted package repositories.
            
            Evidence:
            {evidence}
            
            JSON format:
            {{
                "latest_version": "1.2.3" or null if unable to determine,
                "source": "Name of the source",
                "source_url": "URL of the source",
                "confidence": 0.0 to 1.0
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
                    discovered_version = parsed["latest_version"]
                    broadcast_log(job_id, agent_name, f"Discovered latest version: {discovered_version} from {parsed.get('source_url')}")
                    redis_service.set_latest_version(app_name, os_name, architecture, parsed)
                else:
                    broadcast_log(job_id, agent_name, "LLM could not confidently determine the latest version from evidence.", "warning")
                    version_check_unavailable = True
                    
            except Exception as e:
                logger.error(f"LLM parsing failed: {e}")
                # Fallback to regex extraction
                import re
                matches = re.findall(r'(\d+\.\d+(?:\.\d+)*)', evidence)
                if matches:
                    discovered_version = max(matches, key=lambda v: [int(x) for x in v.split('.')])
                    broadcast_log(job_id, agent_name, f"Fallback: extracted latest version {discovered_version} via regex.")
                else:
                    broadcast_log(job_id, agent_name, "Failed to parse LLM version discovery response and no fallback version found.", "error")
                    version_check_unavailable = True

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED" if not version_check_unavailable else "FAILED")
    
    updates["discovered_latest_version"] = discovered_version
    updates["version_check_unavailable"] = version_check_unavailable
    
    return updates
