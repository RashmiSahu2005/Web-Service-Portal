import socket
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def validate_request(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ValidationAgent"
    stage_name = "DEVICE_VALIDATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting validation")
    
    updates = {"current_stage": "VALIDATION"}
    
    if not state.get("application_name"):
        error_message = "Application name is missing"
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    if settings.USE_FLEETDM:
        hostname = socket.gethostname()
        host_info = FleetDMService.get_host_info(hostname)
        
        if not host_info:
            error_message = f"FleetDM Host '{hostname}' not found or offline."
            broadcast_log(job_id, agent_name, error_message, "error")
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {**updates, "status": "FAILED", "error_message": error_message}
            
        battery_level = 100
        if "batteries" in host_info and host_info["batteries"]:
            battery_level = host_info["batteries"][0].get("percent", 100)
            
        min_battery = state.get("minimum_battery_percentage", 30)
        
        if battery_level < min_battery:
            error_message = f"Battery level ({battery_level}%) is below the required threshold ({min_battery}%)."
            broadcast_log(job_id, agent_name, error_message, "error")
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {**updates, "status": "FAILED", "error_message": error_message}
            
        if host_info.get("status") != "online":
            error_message = "Host is not online."
            broadcast_log(job_id, agent_name, error_message, "error")
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {**updates, "status": "FAILED", "error_message": error_message}
            
        broadcast_log(job_id, agent_name, f"Host {hostname} validated successfully (Battery: {battery_level}%)")
        
    broadcast_log(job_id, agent_name, "Validation successful")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
