from app.graph.state import InstallationState
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.fleetdm_service import FleetDMService

def installation_script_cleanup(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "CleanupAgent"
    stage_name = "INSTALLATION_SCRIPT_CLEANUP"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Cleaning up temporary installation scripts")
    
    updates = {
        "installation_script_deleted": {},
        "installation_cleanup_error": {}
    }
    
    fleet_script_ids = state.get("fleet_script_ids", {})
    script_reused = state.get("script_reused", {})
    
    if not fleet_script_ids:
        broadcast_log(job_id, agent_name, "No temporary scripts found to clean up.")
    
    for sig, script_id in fleet_script_ids.items():
        if script_reused.get(sig):
            broadcast_log(job_id, agent_name, f"[{sig}] Script ID {script_id} was reused from registry. Skipping deletion.")
            updates["installation_script_deleted"][sig] = False
            continue
            
        script_registry_ids = state.get("script_registry_ids", {})
        if sig in script_registry_ids:
            broadcast_log(job_id, agent_name, f"[{sig}] Script ID {script_id} was successfully saved to Script Registry. Skipping deletion.")
            updates["installation_script_deleted"][sig] = False
            continue
            
        broadcast_log(job_id, agent_name, f"[{sig}] Deleting FleetDM script ID {script_id}")
        success = FleetDMService.delete_script(int(script_id))
        
        if success:
            updates["installation_script_deleted"][sig] = True
            broadcast_log(job_id, agent_name, f"[{sig}] Successfully deleted script ID {script_id}")
        else:
            updates["installation_script_deleted"][sig] = False
            updates["installation_cleanup_error"][sig] = "Failed to delete script"
            broadcast_log(job_id, agent_name, f"[{sig}] Failed to delete script ID {script_id}", "error")
            
    updates["current_stage"] = "INSTALLATION_SCRIPT_CLEANUP_COMPLETED"
    
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
