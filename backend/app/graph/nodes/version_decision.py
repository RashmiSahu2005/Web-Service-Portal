from app.graph.state import InstallationState
from app.core.logger import logger
from app.graph.nodes.utils import broadcast_stage, broadcast_log
import re
# pyrefly: ignore [missing-import]
from packaging.version import parse as parse_version

def _compare_versions(installed: str, target: str) -> int:
    """
    Returns 1 if installed > target, 0 if equal, -1 if installed < target
    """
    if not installed or not target:
        raise ValueError("Empty version string provided")
    try:
        def clean(v):
            match = re.search(r'\d+(\.\d+)*', str(v))
            return match.group(0) if match else "0"
            
        p_inst = parse_version(clean(installed))
        p_targ = parse_version(clean(target))
        
        if p_inst > p_targ: return 1
        elif p_inst == p_targ: return 0
        else: return -1
    except Exception as e:
        logger.warning(f"Version comparison failed between {installed} and {target}: {e}")
        if installed == target: return 0
        raise ValueError(f"Could not compare {installed} and {target}")

def version_decision(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VersionDecisionAgent"
    stage_name = "VERSION_DECISION"
    
    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}
        
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    
    requested_version = state.get("requested_version")
    version_resolution_source = state.get("version_resolution_source")
    version_availability_status = state.get("version_availability_status")
    
    discovered_version = state.get("discovered_latest_version")
    version_check_unavailable = state.get("version_check_unavailable", False)
    
    if version_availability_status == "CHECK_FAILED":
        broadcast_log(job_id, agent_name, f"Could not determine whether requested version {requested_version} is available.", "error")
        broadcast_log(job_id, agent_name, "Version availability check failed.", "error")
        broadcast_log(job_id, agent_name, "Stopping installation safely.", "error")
        
        application_states = state.get("application_states", {})
        for host, status in application_states.items():
            if status != "NOT_INSTALLED":
                application_states[host] = "VERSION_CHECK_UNAVAILABLE"
                
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {
            "application_states": application_states,
            "hosts_requiring_installation": [],
            "status": "VERSION_CHECK_UNAVAILABLE"
        }
        
    if version_resolution_source == "latest":
        broadcast_log(job_id, agent_name, "No version specified. Using latest version discovery.")
    elif version_resolution_source == "explicit":
        broadcast_log(job_id, agent_name, f"Requested version: {requested_version}")
        broadcast_log(job_id, agent_name, "Exact version is available.")
    elif version_resolution_source == "latest_fallback":
        broadcast_log(job_id, agent_name, f"Requested version: {requested_version}")
        broadcast_log(job_id, agent_name, "Requested version is not available.")
        broadcast_log(job_id, agent_name, f"Falling back to latest version: {discovered_version}")

    if version_resolution_source in ("latest", "latest_fallback"):
        if version_check_unavailable or not discovered_version:
            broadcast_log(job_id, agent_name, "Unable to verify the latest available version. Stopping safely.", "error")
            application_states = state.get("application_states", {})
            for host, status in application_states.items():
                if status != "NOT_INSTALLED":
                    application_states[host] = "VERSION_CHECK_UNAVAILABLE"
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {
                "application_states": application_states,
                "hosts_requiring_installation": [],
                "status": "VERSION_CHECK_UNAVAILABLE"
            }
        actual_target = discovered_version
    else:
        actual_target = requested_version

    if version_resolution_source == "explicit":
        broadcast_log(job_id, agent_name, f"Installing requested version: {actual_target}")
    else:
        broadcast_log(job_id, agent_name, f"Target version: {actual_target}")
        
    broadcast_log(job_id, agent_name, f"Resolution source: {version_resolution_source}")

    installed_versions = state.get("installed_versions", {})
    application_states = state.get("application_states", {})
    hosts_requiring = []
    
    for host_id, inst_ver in installed_versions.items():
        if application_states.get(host_id) == "NOT_INSTALLED":
            hosts_requiring.append(host_id)
            continue
            
        if not actual_target:
            hosts_requiring.append(host_id)
            application_states[host_id] = "OUTDATED"
            continue
            
        try:
            comparison = _compare_versions(inst_ver, actual_target)
            if comparison >= 0:
                application_states[host_id] = "ALREADY_LATEST" if version_resolution_source in ("latest", "latest_fallback") else "ALREADY_TARGET_VERSION"
                broadcast_log(job_id, agent_name, f"Host {host_id} already satisfies version {actual_target}. Skipping.")
            else:
                application_states[host_id] = "OUTDATED"
                broadcast_log(job_id, agent_name, f"Host {host_id} requires update (Installed: {inst_ver}, Target: {actual_target})")
                hosts_requiring.append(host_id)
        except ValueError as e:
            broadcast_log(job_id, agent_name, f"Version comparison unavailable for host {host_id}: {e}", "warning")
            application_states[host_id] = "VERSION_COMPARISON_UNAVAILABLE"
            
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return {
        "target_version": actual_target,
        "version": "latest" if version_resolution_source in ("latest", "latest_fallback") else actual_target,
        "application_states": application_states,
        "hosts_requiring_installation": hosts_requiring
    }
