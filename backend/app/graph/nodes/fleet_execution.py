import os
import tempfile
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.script_registry_service import ScriptRegistryService
import time

def _upload_script(script_content: str, application_id: str, job_id: str, agent_name: str, script_type: str = ".py", os_signature: str = "") -> str:
    broadcast_log(job_id, agent_name, "Starting script upload to FleetDM...")
    
    # TRANSPORT WRAPPER FOR LINUX /tmp/noexec (Architecture Requirement B)
    # FleetDM executes scripts directly via execve. If /tmp is mounted noexec, 
    # executing a script with a shebang fails with EACCES (permission denied).
    # However, if the script has NO shebang, FleetDM natively falls back to 
    # invoking `/bin/sh /tmp/script`. Since `/bin/sh` is the executed binary, 
    # this bypasses the noexec restriction. We then use `bash -s` to pipe the
    # canonical Bash script (which may contain Bash-specific syntax) into Bash.
    if script_type == ".sh" and "windows" not in os_signature.lower():
        script_content = f"bash -s <<'DEPLOYIQ_SCRIPT'\n{script_content}\nDEPLOYIQ_SCRIPT\n"
        
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
        "script_registry_ids": state.get("script_registry_ids", {}),
        "cached_script_failures": state.get("cached_script_failures", {}).copy(),
        "fleet_execution_start_time": state.get("fleet_execution_start_time")
    }
    
    os_groups = state.get("os_groups", {})
    script_reused_map = state.get("script_reused", {})
    script_contents = state.get("script_contents", {})
    hosts_requiring_installation = set(state.get("hosts_requiring_installation", []))
    
    if not updates["fleet_execution_start_time"]:
        updates["fleet_execution_start_time"] = time.time()
    
    if not hosts_requiring_installation:
        broadcast_log(job_id, agent_name, "No hosts require installation. Skipping execution.", "info")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates
        
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - FleetDM upload/execution skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    all_execution_ids = []
    failed_any_new = False   # new scripts that failed upload/exec
    
    for sig, host_ids in os_groups.items():
        # Only execute on hosts that need installation
        target_hosts = [h for h in host_ids if h in hosts_requiring_installation]
        if not target_hosts:
            continue
            
        script_reused = script_reused_map.get(sig, False)
        
        broadcast_log(job_id, agent_name, f"[{sig}] Preparing execution for hosts: {target_hosts}")
        
        if script_reused:
            # --- CACHED SCRIPT PATH ---
            script_id = updates["fleet_script_ids"].get(sig)
            broadcast_log(job_id, agent_name,
                f"[DeployIQ][ScriptRegistry] Application={state.get('application_name')} "
                f"Source=CACHE FleetDM_ID={script_id} Action=REUSE")
            
            # Attempt to run on each target host
            cache_exec_ids = []
            cache_failed = False
            cache_error_reason = ""
            
            for host_id in target_hosts:
                try:
                    exec_id = _execute_on_host(host_id, script_id, job_id, agent_name)
                    if exec_id:
                        cache_exec_ids.append(exec_id)
                        all_execution_ids.append(exec_id)
                    else:
                        # _execute_on_host returned None — likely a 404 or HTTP error
                        cache_failed = True
                        cache_error_reason = f"FleetDM returned no execution_id for script_id={script_id} on host {host_id}"
                except Exception as e:
                    error_str = str(e)
                    broadcast_log(job_id, agent_name,
                        f"[{sig}] Cached script execution error: {error_str}", "error")
                    cache_failed = True
                    cache_error_reason = error_str
                    
            if cache_failed and not cache_exec_ids:
                # Record as a cache failure — do NOT set status=FAILED here.
                # script_failure_analysis will handle invalidation + regeneration.
                broadcast_log(job_id, agent_name,
                    f"[DeployIQ][ScriptRegistry] Application={state.get('application_name')} "
                    f"Source=CACHE FleetDM_ID={script_id} Status=FAILED "
                    f"Reason={cache_error_reason} Action=INVALIDATE_AND_REGENERATE")
                updates["cached_script_failures"][sig] = {
                    "fleet_script_id": str(script_id),
                    "reason": "FleetDM execution failed for cached script",
                    "error_message": cache_error_reason
                }
                # Don't add to all_execution_ids — monitoring will skip this sig
                continue
            elif cache_exec_ids:
                AgentEventService.broadcast_fleet_execution(
                    job_id=job_id,
                    script_id=script_id,
                    execution_ids=cache_exec_ids,
                    host_ids=target_hosts
                )
        else:
            # --- NEW SCRIPT GENERATION PATH ---
            script_content = script_contents.get(sig)
            script_type = state.get("current_script_type", {}).get(sig, ".py")
            if not script_content:
                broadcast_log(job_id, agent_name, f"[{sig}] Missing script content.", "error")
                failed_any_new = True
                continue
                
            script_id = _upload_script(script_content, state.get("application_id", ""), job_id, agent_name, script_type, sig)
            if not script_id:
                broadcast_log(job_id, agent_name, f"[{sig}] FleetDM upload failed.", "error")
                failed_any_new = True
                continue
                
            updates["fleet_script_ids"][sig] = script_id
            
            broadcast_log(job_id, agent_name,
                f"[DeployIQ][ScriptGeneration] Application={state.get('application_name')} "
                f"Attempt={state.get('current_attempts', {}).get(sig, 1)}/3 "
                f"ScriptType={script_type} FleetDM_ID={script_id} Action=UPLOAD_AND_EXECUTE")
                
            execution_ids_local = []
            for host_id in target_hosts:
                exec_id = _execute_on_host(host_id, script_id, job_id, agent_name)
                if exec_id:
                    execution_ids_local.append(exec_id)
                    all_execution_ids.append(exec_id)
                    
            if not execution_ids_local:
                broadcast_log(job_id, agent_name, f"[{sig}] Execution failed on all target hosts.", "error")
                failed_any_new = True
            else:
                AgentEventService.broadcast_fleet_execution(
                    job_id=job_id,
                    script_id=script_id,
                    execution_ids=execution_ids_local,
                    host_ids=target_hosts
                )
            
    updates["execution_ids"] = all_execution_ids
    
    # Only hard-fail if newly generated scripts couldn't execute AND no cached scripts are pending
    # Cached script failures are handled by script_failure_analysis.
    has_cached_failures = bool(updates.get("cached_script_failures"))
    
    if failed_any_new and not all_execution_ids and not has_cached_failures:
        error_message = "Execution failed on all hosts across all OS groups."
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    if all_execution_ids:
        broadcast_log(job_id, agent_name, f"Execution started successfully: {', '.join(all_execution_ids)}")
        
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
