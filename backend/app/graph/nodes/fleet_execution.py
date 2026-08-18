import os
import tempfile
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.script_registry_service import ScriptRegistryService

def _upload_script(script_content: str, application_id: str, job_id: str, agent_name: str, script_type: str = ".py") -> str:
    broadcast_log(job_id, agent_name, "Starting script upload to FleetDM...")
    
    fd, temp_path = tempfile.mkstemp(prefix=f"apphub_{application_id}_", suffix=script_type)
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
            
        broadcast_log(job_id, agent_name, f"Script uploaded successfully. Fleet Script ID: {script_id}")
        return str(script_id)
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error during FleetDM upload: {e}", "error")
        return None
    finally:
        try:
            os.remove(temp_path)
        except OSError as e:
            broadcast_log(job_id, agent_name, f"Failed to clean up temporary script file {temp_path}: {e}", "warning")

def _execute_on_host(host_id: int, script_id: str, job_id: str, agent_name: str) -> str:
    broadcast_log(job_id, agent_name, f"Starting execution on host {host_id} with script ID {script_id}...")
    try:
        response = FleetDMService.run_script(host_id, script_id)
        if not response:
            broadcast_log(job_id, agent_name, f"Host {host_id} execution failed (empty response).", "error")
            return None
            
        execution_id = response.get("execution_id")
        if not execution_id:
            broadcast_log(job_id, agent_name, f"Missing execution_id from FleetDM for host {host_id}. Response: {response}", "error")
            return None
            
        broadcast_log(job_id, agent_name, f"Execution started successfully on host {host_id}. Execution ID: {execution_id}")
        return str(execution_id)
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Host {host_id} execution failed: {e}", "error")
        return None

async def execute_fleet(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "FleetExecutionAgent"
    stage_name = "FLEET_UPLOAD"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting FleetDM execution preparation for OS groups")
    
    updates = {
        "current_stage": "FLEET_EXECUTION_STARTED",
        "fleet_script_ids": state.get("fleet_script_ids", {}),
        "execution_ids": [],
        "script_registry_ids": state.get("script_registry_ids", {})
    }
    
    os_groups = state.get("os_groups", {})
    script_reused_map = state.get("script_reused", {})
    script_contents = state.get("script_contents", {})
    hosts_requiring_installation = set(state.get("hosts_requiring_installation", []))
    
    if not hosts_requiring_installation:
        broadcast_log(job_id, agent_name, "No hosts require installation. Skipping execution.", "info")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates
        
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - FleetDM upload/execution skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    all_execution_ids = []
    failed_any = False
    
    for sig, host_ids in os_groups.items():
        # Only execute on hosts that need installation
        target_hosts = [h for h in host_ids if h in hosts_requiring_installation]
        if not target_hosts:
            continue
            
        os_name, arch = sig.split("_")
        script_reused = script_reused_map.get(sig, False)
        
        broadcast_log(job_id, agent_name, f"[{sig}] Preparing execution for hosts: {target_hosts}")
        
        if script_reused:
            script_id = updates["fleet_script_ids"].get(sig)
            broadcast_log(job_id, agent_name, f"[{sig}] Reusing FleetDM script ID {script_id}")
        else:
            script_content = script_contents.get(sig)
            script_type = state.get("current_script_type", {}).get(sig, ".py")
            if not script_content:
                broadcast_log(job_id, agent_name, f"[{sig}] Missing script content.", "error")
                failed_any = True
                continue
                
            script_id = _upload_script(script_content, state.get("application_id", ""), job_id, agent_name, script_type)
            if not script_id:
                broadcast_log(job_id, agent_name, f"[{sig}] FleetDM upload failed.", "error")
                failed_any = True
                continue
                
            updates["fleet_script_ids"][sig] = script_id
            
            # Save to Script Registry
            broadcast_log(job_id, agent_name, f"[{sig}] Saving newly uploaded script to Script Registry")
            try:
                registry_entry = ScriptRegistryService.save_script(
                    application_name=state.get("application_name"),
                    version=state.get("version"),
                    operating_system=os_name,
                    architecture=arch,
                    fleet_script_id=script_id,
                    script_hash=state.get("script_hashes", {}).get(sig),
                    risk_score=state.get("risk_scores", {}).get(sig),
                    risk_level=state.get("risk_levels", {}).get(sig),
                    risk_reasons=state.get("risk_reasons_map", {}).get(sig)
                )
                updates["script_registry_ids"][sig] = registry_entry.registry_id
            except Exception as e:
                broadcast_log(job_id, agent_name, f"[{sig}] Failed to save to script registry: {e}", "warning")
                
        execution_ids_local = []
        for host_id in target_hosts:
            exec_id = _execute_on_host(host_id, script_id, job_id, agent_name)
            if exec_id:
                execution_ids_local.append(exec_id)
                all_execution_ids.append(exec_id)
                
        if not execution_ids_local:
            broadcast_log(job_id, agent_name, f"[{sig}] Execution failed on all target hosts.", "error")
            failed_any = True
        else:
            AgentEventService.broadcast_fleet_execution(
                job_id=job_id,
                script_id=script_id,
                execution_ids=execution_ids_local,
                host_ids=target_hosts
            )
            
    updates["execution_ids"] = all_execution_ids
    
    if failed_any and not all_execution_ids:
        error_message = "Execution failed on all hosts across all OS groups."
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    broadcast_log(job_id, agent_name, f"Execution started successfully: {', '.join(all_execution_ids)}")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
