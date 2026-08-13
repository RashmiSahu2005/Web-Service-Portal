from app.graph.state import InstallationState
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.fleetdm_service import FleetDMService

def verification_script_cleanup(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VerificationCleanupAgent"
    stage_name = "VERIFICATION_SCRIPT_CLEANUP"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Cleaning up temporary verification scripts")
    
    updates = {
        "verification_script_deleted": {},
        "verification_cleanup_error": {}
    }
    
    fleet_script_ids = state.get("verification_fleet_script_ids", {})
    
    if not fleet_script_ids:
        broadcast_log(job_id, agent_name, "No temporary verification scripts found to clean up.")
    
    for sig, script_id in fleet_script_ids.items():
        broadcast_log(job_id, agent_name, f"[{sig}] Deleting FleetDM verification script ID {script_id}")
        success = FleetDMService.delete_script(int(script_id))
        
        if success:
            updates["verification_script_deleted"][sig] = True
            broadcast_log(job_id, agent_name, f"[{sig}] Successfully deleted verification script ID {script_id}")
        else:
            updates["verification_script_deleted"][sig] = False
            updates["verification_cleanup_error"][sig] = "Failed to delete script"
            broadcast_log(job_id, agent_name, f"[{sig}] Failed to delete verification script ID {script_id}", "error")
            
    updates["current_stage"] = "VERIFICATION_SCRIPT_CLEANUP_COMPLETED"
    
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
