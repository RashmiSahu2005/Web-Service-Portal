import time
import asyncio
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.agent_event_service import AgentEventService

async def verification_monitoring(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VerificationMonitoringAgent"
    stage_name = "VERIFICATION_MONITORING"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting verification execution monitoring")
    
    updates = {"current_stage": "VERIFICATION_MONITORING", "verification_execution_results": {}}
    
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK", "CANCELLED"]:
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Verification Monitoring skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        updates["verification_result"] = True
        return updates
        
    execution_ids = state.get("verification_execution_ids", [])
    if not execution_ids:
        broadcast_log(job_id, agent_name, "No verification execution IDs to monitor.", "info")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates
        
    host_ids = state.get("hosts_requiring_installation", state.get("host_ids", []))
    exec_to_host = {}
    for i, exec_id in enumerate(execution_ids):
        host_id = host_ids[i] if i < len(host_ids) else "Unknown"
        exec_to_host[exec_id] = host_id
        
    pending_executions = set(execution_ids)
    failed_executions = set()
    verification_results = {}
    
    start_time = time.time()
    max_timeout = settings.VERIFICATION_COMMAND_TIMEOUT
    polling_interval = settings.POLLING_INTERVAL
    
    while pending_executions:
        elapsed = time.time() - start_time
        timeout_reached = elapsed > max_timeout
        
        for exec_id in list(pending_executions):
            host_id = exec_to_host.get(exec_id)
            broadcast_log(job_id, agent_name, f"Monitoring verification execution {exec_id} for Host {host_id}... (Elapsed: {int(elapsed)}s)")
            
            result = FleetDMService.get_script_result(exec_id)
            
            if not result:
                broadcast_log(job_id, agent_name, f"Failed to get verification result for execution {exec_id} (Host {host_id}).", "error")
                failed_executions.add(exec_id)
                verification_results[str(host_id)] = False
                pending_executions.remove(exec_id)
                continue
                
            exit_code = result.get("exit_code")
            output = result.get("output", "")
            
            updates["verification_execution_results"][exec_id] = result
            
            if exit_code is not None or result.get("host_timeout"):
                if exit_code == 0:
                    broadcast_log(job_id, agent_name, f"Host {host_id} verification returned exit_code=0 (COMPLETED)")
                    verification_results[str(host_id)] = True
                else:
                    broadcast_log(job_id, agent_name, f"Host {host_id} verification returned exit_code={exit_code} or timed out (FAILED)", "warning")
                    failed_executions.add(exec_id)
                    verification_results[str(host_id)] = False
                    
                pending_executions.remove(exec_id)
            else:
                broadcast_log(job_id, agent_name, f"Host {host_id} verification is still running")

        if timeout_reached and pending_executions:
            broadcast_log(job_id, agent_name, f"Verification monitoring timed out after {max_timeout} seconds.", "error")
            for exec_id in list(pending_executions):
                host_id = exec_to_host.get(exec_id)
                failed_executions.add(exec_id)
                verification_results[str(host_id)] = False
                if exec_id not in updates["verification_execution_results"]:
                    updates["verification_execution_results"][exec_id] = {}
                updates["verification_execution_results"][exec_id]["host_timeout"] = True
                updates["verification_execution_results"][exec_id]["output"] = "Verification timed out"
            break

        if pending_executions:
            await asyncio.sleep(polling_interval)

    updates["verification_results"] = verification_results

    # Broadcast to UI
    AgentEventService.broadcast_verification(
        job_id=job_id,
        verification_result=len(failed_executions) == 0,
        verification_results=verification_results
    )

    if failed_executions:
        broadcast_log(job_id, agent_name, "Verification failed due to one or more host failures.", "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        updates["verification_result"] = False
        # Do not fail the whole graph yet, we must proceed to verification cleanup
        return {**updates}
        
    broadcast_log(job_id, agent_name, "Overall verification completed successfully on all hosts.")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    updates["verification_result"] = True
    
    return {**updates}
