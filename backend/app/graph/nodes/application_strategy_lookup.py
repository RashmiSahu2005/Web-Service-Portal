from app.graph.state import InstallationState
from app.services.application_strategy_service import ApplicationStrategyService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def application_strategy_lookup(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationStrategyLookupAgent"
    stage_name = "APPLICATION_STRATEGY_LOOKUP"
    
    # Check cancellation
    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}
        
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Looking up cached application installation strategies")
    
    app_name = state.get("application_name")
    os_groups = state.get("os_groups", {})
    
    updates = {
        "strategies": {},
        "strategy_reused": {}
    }
    
    for sig, host_ids in os_groups.items():
        # sig format: Ubuntu_amd64 or Ubuntu_24.04_amd64
        parts = sig.split("_")
        os_name = parts[0]
        arch = parts[-1]
        os_version = parts[1] if len(parts) > 2 else ""
        
        broadcast_log(job_id, agent_name, f"Looking up cached strategy for {app_name} on {sig}")
        
        strategy = ApplicationStrategyService.get_strategy(app_name, os_name, os_version, arch)
        
        if strategy:
            broadcast_log(job_id, agent_name, f"✓ Cached strategy reused for {sig}")
            updates["strategies"][sig] = {
                "package_manager": strategy.package_manager,
                "package_name": strategy.package_name,
                "installation_method": strategy.installation_method,
                "installed_version_command": strategy.installed_version_command,
                "latest_version_command": strategy.latest_version_command,
                "latest_version_source": strategy.latest_version_source,
                "verification_command": strategy.verification_command
            }
            updates["strategy_reused"][sig] = True
        else:
            broadcast_log(job_id, agent_name, f"No cached strategy found for {sig}. Strategy discovery required.")
            updates["strategy_reused"][sig] = False
            
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
