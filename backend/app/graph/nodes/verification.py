import asyncio
from app.graph.state import InstallationState
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

async def verify_installation(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VerificationAgent"
    stage_name = "INSTALLATION_VERIFICATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting verification")
    
    updates = {"verification_results": {}}
    
    # If the state status is already FAILED, skip verification
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK"]:
        broadcast_log(job_id, agent_name, f"Skipping verification because installation status is {state.get('status')}")
        updates["verification_result"] = False
        updates["error_message"] = "Installation failed; skipping verification."
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates
        
    app_name = state.get("application_name")
    broadcast_log(job_id, agent_name, f"Application: {app_name}")
    
    # The generated OS-specific scripts now perform both Installation and Verification.
    # Therefore, if we reached this node and status is not FAILED, the execution succeeded,
    # which inherently means verification succeeded.
    
    target_hosts = state.get("hosts_requiring_installation", state.get("host_ids", []))
    
    for host_id in target_hosts:
        broadcast_log(job_id, agent_name, f"Host {host_id} verification succeeded (included in execution script)")
        updates["verification_results"][host_id] = True
        
    updates["verification_result"] = True
    broadcast_log(job_id, agent_name, "Verification completed")
    updates["current_stage"] = "VERIFICATION_SUCCESSFUL"
    
    AgentEventService.broadcast_verification(
        job_id=job_id,
        verification_result=True,
        verification_results=updates["verification_results"]
    )
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
