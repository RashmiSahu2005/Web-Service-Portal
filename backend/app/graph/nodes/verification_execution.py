import os
import tempfile
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def _upload_verification_script(script_content: str, application_id: str, job_id: str, agent_name: str, script_type: str = ".py") -> str:
    broadcast_log(job_id, agent_name, "Starting verification script upload to FleetDM...")
    
    fd, temp_path = tempfile.mkstemp(prefix=f"apphub_{application_id}_verify_", suffix=script_type)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(script_content)
            
        response = FleetDMService.upload_script(temp_path)
        
        if not response:
            broadcast_log(job_id, agent_name, "FleetDMService returned empty response for script upload.", "error")
            return None
            
        script_data = response.get("script", {})
        script_id = script_data.get("id") or response.get("id") or response.get("script_id")
        
        if not script_id:
            broadcast_log(job_id, agent_name, f"Missing script ID in FleetDM response. Response: {response}", "error")
            return None
            
        broadcast_log(job_id, agent_name, f"Verification script uploaded successfully. Fleet Script ID: {script_id}")
        return str(script_id)
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error during FleetDM upload: {e}", "error")
        return None
    finally:
        try:
            os.remove(temp_path)
        except OSError as e:
            pass

def _execute_on_host(host_id: int, script_id: str, job_id: str, agent_name: str) -> str:
    broadcast_log(job_id, agent_name, f"Starting verification on host {host_id} with script ID {script_id}...")
    try:
        response = FleetDMService.run_script(host_id, script_id)
        if not response:
            broadcast_log(job_id, agent_name, f"Host {host_id} verification execution failed (empty response).", "error")
            return None
            
        execution_id = response.get("execution_id")
        if not execution_id:
            return None
            
        broadcast_log(job_id, agent_name, f"Verification started successfully on host {host_id}. Execution ID: {execution_id}")
        return str(execution_id)
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Host {host_id} verification execution failed: {e}", "error")
        return None

async def verification_execution(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VerificationExecutionAgent"
    stage_name = "VERIFICATION_EXECUTION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    
    # If the state status is already FAILED or CANCELLED, skip verification
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK", "CANCELLED"]:
        broadcast_log(job_id, agent_name, f"Skipping verification because status is {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return {"verification_result": False}

    updates = {
        "current_stage": "VERIFICATION_EXECUTION_STARTED",
        "verification_fleet_script_ids": state.get("verification_fleet_script_ids", {}),
        "verification_execution_ids": []
    }
    
    os_groups = state.get("os_groups", {})
    script_contents = state.get("verification_script_contents", {})
    hosts_requiring_installation = set(state.get("hosts_requiring_installation", []))
    
    if not hosts_requiring_installation:
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates
        
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Verification execution skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    all_execution_ids = []
    failed_any = False
    
    for sig, host_ids in os_groups.items():
        target_hosts = [h for h in host_ids if h in hosts_requiring_installation]
        if not target_hosts:
            continue
            
        script_content = script_contents.get(sig)
        os_name = sig.split("_")[0]
        script_type = ".ps1" if os_name == "Windows" else ".py"
        
        if not script_content:
            broadcast_log(job_id, agent_name, f"[{sig}] Missing verification script content.", "error")
            failed_any = True
            continue
            
        script_id = _upload_verification_script(script_content, state.get("application_id", ""), job_id, agent_name, script_type)
        if not script_id:
            broadcast_log(job_id, agent_name, f"[{sig}] Verification upload failed.", "error")
            failed_any = True
            continue
            
        updates["verification_fleet_script_ids"][sig] = script_id
                
        execution_ids_local = []
        for host_id in target_hosts:
            exec_id = _execute_on_host(host_id, script_id, job_id, agent_name)
            if exec_id:
                execution_ids_local.append(exec_id)
                all_execution_ids.append(exec_id)
                
        if not execution_ids_local:
            broadcast_log(job_id, agent_name, f"[{sig}] Verification execution failed on all target hosts.", "error")
            failed_any = True
            
    updates["verification_execution_ids"] = all_execution_ids
    
    if failed_any and not all_execution_ids:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": "Verification execution failed on all hosts."}
        
    broadcast_log(job_id, agent_name, f"Verification execution started: {', '.join(all_execution_ids)}")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
