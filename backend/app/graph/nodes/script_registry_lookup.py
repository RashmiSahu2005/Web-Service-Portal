from app.graph.state import InstallationState
from app.services.script_registry_service import ScriptRegistryService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.agent_event_service import AgentEventService

def script_registry_lookup(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptRegistryAgent"
    stage_name = "SCRIPT_REGISTRY_LOOKUP"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Looking up compatible script in registry")
    
    updates = {}
    
    # If the state status is already FAILED, skip
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK"]:
        broadcast_log(job_id, agent_name, f"Skipping lookup because installation status is {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates
        
    app_name = state.get("application_name")
    version = state.get("version")
    os_groups = state.get("os_groups", {})
    
    updates["script_registry_ids"] = {}
    updates["script_hashes"] = {}
    updates["script_hashes"] = {}
    updates["risk_scores"] = {}
    updates["risk_levels"] = {}
    updates["risk_reasons_map"] = {}
    
    all_reused = True
    
    for sig in os_groups.keys():
        os_name, arch = sig.split("_")
        
        broadcast_log(job_id, agent_name, f"Searching for compatible ACTIVE script for {sig}")
        
        script = ScriptRegistryService.find_compatible_script(
            application_name=app_name,
            version=version,
            operating_system=os_name,
            architecture=arch
        )
        
        if script:
            broadcast_log(job_id, agent_name, f"Compatible script found for {sig}. Registry ID={script.registry_id} (Fleet script ID {script.fleet_script_id} will NOT be reused)")
            
            updates["script_registry_ids"][sig] = script.registry_id
            updates["script_hashes"][sig] = script.script_hash
            updates["risk_scores"][sig] = script.risk_score
            updates["risk_levels"][sig] = script.risk_level
            updates["risk_reasons_map"][sig] = script.risk_reasons
            
            AgentEventService.broadcast_risk(
                job_id,
                script.risk_score,
                script.risk_level,
                script.risk_reasons
            )
        else:
            broadcast_log(job_id, agent_name, f"No compatible ACTIVE script found for {sig}")
            
    updates["regeneration_count"] = state.get("regeneration_count", 0)
    updates["current_stage"] = "SCRIPT_GENERATION_REQUIRED"
        
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
