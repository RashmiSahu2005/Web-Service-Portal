import asyncio
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log

async def detect_os(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "OSDetectionAgent"
    stage_name = "OS_DETECTION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting OS Detection")
    
    updates = {
        "current_stage": stage_name,
        "os_details": {},
        "os_groups": {}
    }
    
    host_ids = state.get("host_ids", [])
    if not host_ids:
        error_message = "No hosts discovered, skipping OS detection."
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "FleetDM disabled. Mocking OS detection for all hosts.")
        for host_id in host_ids:
            if host_id == 1:
                os_name, os_version, arch = "Ubuntu", "22.04 LTS", "amd64"
            elif host_id == 2:
                os_name, os_version, arch = "Ubuntu", "22.04 LTS", "arm64"
            elif host_id == 3:
                os_name, os_version, arch = "Windows", "11", "x64"
            elif host_id == 4:
                os_name, os_version, arch = "macOS", "14.4", "arm64"
            elif host_id == 5:
                os_name, os_version, arch = "Solaris", "11.4", "sparc"
            else:
                os_name, os_version, arch = "Ubuntu", "22.04 LTS", "amd64"
                
            os_detail = {
                "os": os_name,
                "os_version": os_version,
                "architecture": arch
            }
            updates["os_details"][host_id] = os_detail
            sig = f"{os_name}_{arch}"
            if sig not in updates["os_groups"]:
                updates["os_groups"][sig] = []
            updates["os_groups"][sig].append(host_id)
            broadcast_log(job_id, agent_name, f"Host {host_id} OS signature: {sig}")
            
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    # We need to lookup each host_id via FleetDM
    # But FleetDM's get_host_info uses query=hostname. 
    # Luckily, we can query by host_id using GET /api/v1/fleet/hosts/{id}
    # Wait, the current fleetdm_service doesn't have a get_host_by_id method. We can add it!
    # For now, let's assume we implement it.
    
    for host_id in host_ids:
        broadcast_log(job_id, agent_name, f"Detecting OS for host {host_id}...")
        host_info = FleetDMService.get_host_by_id(host_id)
        if not host_info:
            broadcast_log(job_id, agent_name, f"Failed to get info for host {host_id}", "warning")
            continue
            
        platform = host_info.get("platform", "unknown")
        os_version = host_info.get("os_version", "unknown")
        cpu_type = host_info.get("cpu_type", "unknown")
        
        # Normalize architecture
        if cpu_type in ["x86_64", "amd64"]:
            arch = "amd64"
        elif cpu_type in ["arm64", "aarch64"]:
            arch = "arm64"
        else:
            arch = cpu_type
            
        # Normalize OS
        if platform == "ubuntu" or platform == "debian" or "Ubuntu" in os_version:
            os_name = "Ubuntu"
        elif platform == "windows":
            os_name = "Windows"
            arch = "x64" if arch == "amd64" else arch
        elif platform == "darwin":
            os_name = "macOS"
        else:
            os_name = platform.capitalize()
            
        os_detail = {
            "os": os_name,
            "os_version": os_version,
            "architecture": arch
        }
        
        updates["os_details"][host_id] = os_detail
        sig = f"{os_name}_{arch}"
        if sig not in updates["os_groups"]:
            updates["os_groups"][sig] = []
        updates["os_groups"][sig].append(host_id)
        
        broadcast_log(job_id, agent_name, f"Host {host_id} OS signature: {sig}")

    if not updates["os_groups"]:
        error_message = "Failed to detect OS for any host."
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
