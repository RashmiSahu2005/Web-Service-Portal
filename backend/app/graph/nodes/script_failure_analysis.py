from app.graph.state import InstallationState
from app.services.script_registry_service import ScriptRegistryService
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

MAX_SCRIPT_REGENERATIONS = 1

def analyze_script_failure(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptFailureAnalyzer"
    stage_name = "SCRIPT_FAILURE_ANALYSIS"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Analyzing execution results to determine failure root cause")
    
    updates = {}
    
    # If the state status is not FAILED, we assume execution was successful.
    if state.get("status") != "FAILED":
        broadcast_log(job_id, agent_name, "Execution was successful, proceeding normally.")
        
        # Update registry to record success
        registry_id = state.get("script_registry_id")
        if registry_id:
            ScriptRegistryService.update_script_execution(registry_id, success=True)
            
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates
        
    execution_results = state.get("execution_results", {})
    failed_sigs = set()
    
    fleet_script_ids = state.get("fleet_script_ids", {})
    
    for exec_id, result in execution_results.items():
        exit_code = result.get("exit_code")
        output = result.get("output", "").lower()
        timeout = result.get("host_timeout", False)
        script_id = result.get("script_id")
        
        sig = next((k for k, v in fleet_script_ids.items() if str(v) == str(script_id)), None)
        
        if timeout:
            broadcast_log(job_id, agent_name, f"Execution {exec_id} timed out. Likely host/network issue, treating as script failure for retry.", "warning")
            if sig:
                failed_sigs.add(sig)
            continue
            
        if exit_code is not None and exit_code != 0:
            broadcast_log(job_id, agent_name, f"Execution {exec_id} failed with exit code {exit_code}.", "warning")
            if sig:
                failed_sigs.add(sig)
                
                # Analyze the failure
                broadcast_log(job_id, agent_name, "Captured execution error for LLM analysis")
                analysis_prompt = f"""You are a senior system administrator diagnosing a failed application installation script.

The following script execution failed:
Application: {state.get("application_name")}
Version: {state.get("version")}
OS Signature: {sig}
Exit Code: {exit_code}
Script Type: {state.get("current_script_type", {}).get(sig)}

Execution Output / Error:
{output[-2000:] if output else "No output provided"}

Analyze this failure and provide actionable guidance for generating the next script attempt.
Determine:
1. What failed?
2. Why did it fail? (e.g. package manager issue, permissions, missing path, non-interactive context)
3. Actionable guidance for the next generation attempt to fix the root cause. (e.g. "Do not use winget list, instead check registry directly").

Do not generate a new script. Provide only the concise analysis and guidance."""
                try:
                    failure_analysis = LLMService.generate(analysis_prompt)
                    broadcast_log(job_id, agent_name, f"Root cause identified: {failure_analysis[:100]}...")
                except Exception as e:
                    failure_analysis = f"Failed to perform LLM analysis: {e}"
                    broadcast_log(job_id, agent_name, failure_analysis, "warning")
                    
                if "script_failure_context" not in updates:
                    updates["script_failure_context"] = state.get("script_failure_context", {}).copy()
                if sig not in updates["script_failure_context"]:
                    updates["script_failure_context"][sig] = []
                    
                updates["script_failure_context"][sig].append({
                    "attempt": state.get("current_attempts", {}).get(sig, 1),
                    "exit_code": exit_code,
                    "error_output": output,
                    "failed_script_type": state.get("current_script_type", {}).get(sig),
                    "analysis": failure_analysis
                })
                broadcast_log(job_id, agent_name, f"Passing failure context to ScriptGenerationAgent")
                
    registry_id = state.get("script_registry_id")
    
    if failed_sigs:
        if registry_id:
            broadcast_log(job_id, agent_name, f"Invalidating script registry ID {registry_id}")
            ScriptRegistryService.invalidate_script(registry_id)
            
        updates["current_attempts"] = state.get("current_attempts", {}).copy()
        maximum_attempts = state.get("maximum_attempts", {})
        
        can_retry = False
        for sig in failed_sigs:
            current_attempt = updates["current_attempts"].get(sig, 1)
            max_attempts = maximum_attempts.get(sig, 1)
            
            if current_attempt < max_attempts:
                updates["current_attempts"][sig] = current_attempt + 1
                can_retry = True
                broadcast_log(job_id, agent_name, f"[{sig}] Triggering retry (Attempt {current_attempt + 1}/{max_attempts})", "warning")
            else:
                broadcast_log(job_id, agent_name, f"[{sig}] Max attempts ({max_attempts}) reached.", "error")
        
        if can_retry:
            updates["status"] = "SCRIPT_REGENERATION_TRIGGERED"
            updates["script_reused"] = {}
            updates["fleet_script_ids"] = {}
            broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        else:
            broadcast_log(job_id, agent_name, "Max attempts reached for all failed OS groups. Failing deployment.", "error")
            if registry_id:
                ScriptRegistryService.update_script_execution(registry_id, success=False)
            updates["status"] = "FAILED"
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
    else:
        broadcast_log(job_id, agent_name, "No script failures detected, but status was FAILED. This shouldn't happen.", "warning")
        if registry_id:
            ScriptRegistryService.update_script_execution(registry_id, success=False)
        updates["status"] = "FAILED"
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        
    return updates
