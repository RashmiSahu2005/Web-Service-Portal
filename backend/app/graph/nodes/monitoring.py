import time
import asyncio
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log

async def monitor_execution(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "MonitoringAgent"
    stage_name = "EXECUTION_MONITORING"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting execution monitoring")
    
    updates = {"current_stage": "MONITORING", "execution_results": {}}
    
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Monitoring skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        
        from app.api.routes.installation import ws_manager
        try:
            await ws_manager.broadcast_status(job_id, "COMPLETED", "Completed", 100)
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Broadcast failed: {e}", "warning")
            
        return {**updates, "status": "COMPLETED", "current_stage": "COMPLETED"}
        
    execution_ids = state.get("execution_ids", [])
    if not execution_ids:
        error_message = "Missing execution IDs."
        broadcast_log(job_id, agent_name, "No execution IDs to monitor.", "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    host_ids = state.get("hosts_requiring_installation", state.get("host_ids", []))
    exec_to_host = {}
    for i, exec_id in enumerate(execution_ids):
        host_id = host_ids[i] if i < len(host_ids) else "Unknown"
        exec_to_host[exec_id] = host_id
        
    pending_executions = set(execution_ids)
    failed_executions = set()
    
    updates["status"] = "RUNNING"
    
    from app.api.routes.installation import ws_manager
    try:
        await ws_manager.broadcast_status(job_id, "RUNNING", "Installation", 50)
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Broadcast failed: {e}", "warning")
    
    start_time = time.time()
    max_timeout = settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS
    polling_interval = settings.SCRIPT_POLLING_INTERVAL
    
    current_attempts = state.get("current_attempts", {})
    maximum_attempts = state.get("maximum_attempts", {})
    current_script_types = state.get("current_script_type", {})
    
    os_groups = state.get("os_groups", {})
    host_to_sig = {}
    for sig, h_ids in os_groups.items():
        for h in h_ids:
            host_to_sig[h] = sig
    
    while pending_executions:
        elapsed = time.time() - start_time
        if elapsed > max_timeout:
            broadcast_log(job_id, agent_name, f"Execution monitoring timed out after {max_timeout} seconds.", "error")
            for exec_id in list(pending_executions):
                host_id = exec_to_host.get(exec_id)
                failed_executions.add(exec_id)
                if exec_id not in updates["execution_results"]:
                    updates["execution_results"][exec_id] = {}
                updates["execution_results"][exec_id]["host_timeout"] = True
                updates["execution_results"][exec_id]["output"] = "Execution timed out (15 minutes max)"
                try:
                    await ws_manager.broadcast_log(job_id, f"Script execution TIMED OUT (15 minutes) for Host {host_id}.")
                except Exception:
                    pass
            break
            
        for exec_id in list(pending_executions):
            host_id = exec_to_host.get(exec_id)
            sig = host_to_sig.get(host_id)
            
            attempt = current_attempts.get(sig, 1)
            max_attempt = maximum_attempts.get(sig, 1)
            script_type = current_script_types.get(sig, ".py")
            script_lang = "PowerShell" if script_type == ".ps1" else ("Bash" if script_type == ".sh" else "Python")
            
            broadcast_log(job_id, agent_name, f"Monitoring execution {exec_id} for Host {host_id}... (Elapsed: {int(elapsed)}s)")
            
            result = FleetDMService.get_script_result(exec_id)
            
            if result is None:
                broadcast_log(job_id, agent_name, f"FleetDM API unavailable or failed for execution {exec_id} (Host {host_id}). Will retry.", "warning")
                try:
                    await ws_manager.broadcast_log(job_id, f"Attempt: {attempt}/{max_attempt} | Script: {script_lang} | Execution ID: {exec_id} | Exit Code: RESULT_UNAVAILABLE | Elapsed: {int(elapsed)}s")
                except Exception:
                    pass
                continue
                
            exit_code = result.get("exit_code")
            output = result.get("output", "")
            
            updates["execution_results"][exec_id] = result
            
            try:
                exit_str = "null" if exit_code is None else str(exit_code)
                await ws_manager.broadcast_log(job_id, f"Attempt: {attempt}/{max_attempt} | Script: {script_lang} | Execution ID: {exec_id} | Exit Code: {exit_str} | Elapsed: {int(elapsed)}s")
            except Exception:
                pass
                
            if exit_code is not None or result.get("host_timeout"):
                if exit_code == 0:
                    broadcast_log(job_id, agent_name, f"Host {host_id} returned exit_code=0 (SUCCESS)")
                    try:
                        await ws_manager.broadcast_log(job_id, f"Script execution finished with exit code 0 for Host {host_id}.")
                    except Exception:
                        pass
                else:
                    if result.get("host_timeout") or (output and "TimeoutExpired" in output):
                        broadcast_log(job_id, agent_name, f"Host {host_id} execution TIMEOUT", "warning")
                        try:
                            await ws_manager.broadcast_log(job_id, f"Script execution TIMED OUT for Host {host_id}.")
                        except Exception:
                            pass
                    elif result.get("host_offline"):
                        broadcast_log(job_id, agent_name, f"Host {host_id} execution HOST_OFFLINE", "error")
                    else:
                        broadcast_log(job_id, agent_name, f"Host {host_id} returned exit_code={exit_code} (SCRIPT_FAILURE)", "warning")
                        try:
                            await ws_manager.broadcast_log(job_id, f"Script execution failed for Host {host_id} with exit code {exit_code}.")
                        except Exception:
                            pass
                    failed_executions.add(exec_id)
                    
                pending_executions.remove(exec_id)

        if pending_executions:
            await asyncio.sleep(polling_interval)

    if failed_executions:
        broadcast_log(job_id, agent_name, "Overall deployment failed due to one or more host failures.", "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        try:
            await ws_manager.broadcast_status(job_id, "FAILED", "Completed", 100)
        except Exception:
            pass
        return {**updates, "status": "FAILED", "current_stage": "COMPLETED", "error_message": "Execution failed on one or more hosts."}
        
    broadcast_log(job_id, agent_name, "Overall deployment completed successfully on all hosts.")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    try:
        await ws_manager.broadcast_status(job_id, "COMPLETED", "Completed", 100)
    except Exception:
        pass
    
    return {**updates, "status": "COMPLETED", "current_stage": "COMPLETED"}
