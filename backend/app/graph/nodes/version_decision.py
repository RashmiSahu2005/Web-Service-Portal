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
    
    applications = state.get("applications", [])
    installed_versions = state.get("installed_versions", {})
    application_states = state.get("application_states", {})
    hosts_requiring = []
    
    active_app_name = state.get("application_name")
    active_app = None
    
    for app in applications:
        app_name = app.get("name") or app.get("application_name")
        if app_name != active_app_name:
            continue
            
        active_app = app
        requested_version = app.get("requested_version")
        version_resolution_source = app.get("version_resolution_source")
        version_availability_status = app.get("version_availability_status")
        discovered_version = app.get("discovered_latest_version")
        version_check_unavailable = app.get("version_check_unavailable", False)
        
        if app.get("status") in ["FAILED", "CANCELLED"]:
            continue
            
        if version_availability_status == "CHECK_FAILED":
            broadcast_log(job_id, agent_name, f"[{app_name}] Could not determine whether requested version {requested_version} is available.", "error")
            broadcast_log(job_id, agent_name, f"[{app_name}] Version availability check failed. Stopping safely for this app.", "error")
            
            for host, apps_states in application_states.items():
                if apps_states.get(app_name) != "NOT_INSTALLED":
                    apps_states[app_name] = "VERSION_CHECK_UNAVAILABLE"
                    
            app["status"] = "FAILED"
            continue
            
        if version_resolution_source == "latest":
            broadcast_log(job_id, agent_name, f"[{app_name}] No version specified. Using latest version discovery.")
        elif version_resolution_source == "explicit":
            broadcast_log(job_id, agent_name, f"[{app_name}] Requested version: {requested_version}")
            broadcast_log(job_id, agent_name, f"[{app_name}] Exact version is available.")
        elif version_resolution_source == "latest_fallback":
            broadcast_log(job_id, agent_name, f"[{app_name}] Requested version: {requested_version}")
            broadcast_log(job_id, agent_name, f"[{app_name}] Requested version is not available.")
            broadcast_log(job_id, agent_name, f"[{app_name}] Falling back to latest version: {discovered_version}")

        if version_resolution_source in ("latest", "latest_fallback"):
            if version_check_unavailable or not discovered_version:
                broadcast_log(job_id, agent_name, f"[{app_name}] Unable to verify the latest available version. Stopping safely.", "error")
                for host, apps_states in application_states.items():
                    if apps_states.get(app_name) != "NOT_INSTALLED":
                        apps_states[app_name] = "VERSION_CHECK_UNAVAILABLE"
                app["status"] = "FAILED"
                continue
            actual_target = discovered_version
        else:
            actual_target = requested_version

        if version_resolution_source == "explicit":
            broadcast_log(job_id, agent_name, f"[{app_name}] Installing requested version: {actual_target}")
        else:
            broadcast_log(job_id, agent_name, f"[{app_name}] Target version: {actual_target}")
            
        app["target_version"] = actual_target
            
        for host_id, apps_inst_vers in installed_versions.items():
            inst_ver = apps_inst_vers.get(app_name)
            
            state_val = application_states.get(host_id, {}).get(app_name)
            if state_val in ["NOT_INSTALLED", "STATE_CHECK_UNAVAILABLE", "CHECK_FAILED"]:
                if host_id not in hosts_requiring: hosts_requiring.append(host_id)
                app["state"] = "INSTALL_REQUIRED"
                continue
                
            if not actual_target:
                if host_id not in hosts_requiring: hosts_requiring.append(host_id)
                application_states.get(host_id, {})[app_name] = "OUTDATED"
                app["state"] = "INSTALL_REQUIRED"
                continue
                
            try:
                comparison = _compare_versions(inst_ver, actual_target)
                if comparison == 0:
                    state_name = "NO_UPDATE_REQUIRED" if app.get("operation") == "UPDATE" else "ALREADY_TARGET_VERSION"
                    application_states.get(host_id, {})[app_name] = state_name
                    broadcast_log(job_id, agent_name, f"[{app_name}] Host {host_id} already satisfies version {actual_target}. Skipping.")
                elif comparison > 0:
                    if version_resolution_source in ("latest", "latest_fallback"):
                        application_states.get(host_id, {})[app_name] = "VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST"
                        app["status"] = "FAILED"
                        broadcast_log(job_id, agent_name, f"[{app_name}] Host {host_id} has newer version {inst_ver} than target {actual_target}. Downgrade requires explicit request.", "error")
                    else:
                        application_states.get(host_id, {})[app_name] = "DOWNGRADE_REQUESTED"
                        broadcast_log(job_id, agent_name, f"[{app_name}] Host {host_id} explicit downgrade requested (Installed: {inst_ver}, Target: {actual_target})")
                        if host_id not in hosts_requiring: hosts_requiring.append(host_id)
                        app["state"] = "INSTALL_REQUIRED"
                else:
                    application_states.get(host_id, {})[app_name] = "OUTDATED"
                    broadcast_log(job_id, agent_name, f"[{app_name}] Host {host_id} requires update (Installed: {inst_ver}, Target: {actual_target})")
                    if host_id not in hosts_requiring: hosts_requiring.append(host_id)
                    app["state"] = "INSTALL_REQUIRED"
            except ValueError as e:
                broadcast_log(job_id, agent_name, f"[{app_name}] Version comparison unavailable for host {host_id}: {e}", "warning")
                application_states.get(host_id, {})[app_name] = "VERSION_COMPARISON_UNAVAILABLE"
                # Do not fail the app if we just can't compare versions - try to install/verify instead
                if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                    if host_id not in hosts_requiring: hosts_requiring.append(host_id)
                    app["state"] = "INSTALL_REQUIRED"
                
    if active_app and active_app.get("status") == "FAILED":
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {
            "application_states": application_states,
            "hosts_requiring_installation": [],
            "status": "FAILED",
            "applications": applications
        }
        
    # Prepare flattened data for UI
    from app.services.agent_event_service import AgentEventService
    
    flat_app_states = {}
    flat_installed = {}
    flat_available = {}
    
    first_host_id = list(application_states.keys())[0] if application_states else None
    
    for app in applications:
        name = app.get("name") or app.get("application_name")
        if first_host_id and name in application_states.get(first_host_id, {}):
            flat_app_states[name] = application_states[first_host_id][name]
        if first_host_id and name in installed_versions.get(first_host_id, {}):
            flat_installed[name] = installed_versions[first_host_id][name]
        flat_available[name] = app.get("target_version")
        
    AgentEventService.broadcast_application_state(
        job_id,
        application_states=flat_app_states,
        installed_versions=flat_installed,
        available_versions=flat_available
    )
    
    updates = {
        "applications": applications,
        "application_states": application_states,
        "hosts_requiring_installation": hosts_requiring,
        "target_version": active_app.get("target_version") if active_app else None
    }
    
    if not hosts_requiring:
        updates["status"] = "COMPLETED"
        broadcast_log(job_id, agent_name, f"No hosts require installation for active app: {active_app_name}")
        
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
