import os
import tempfile
import subprocess
from app.graph.state import InstallationState
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def validate_script(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptValidationAgent"
    stage_name = "SCRIPT_VALIDATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Statically validating generated scripts...")
    
    os_groups = state.get("os_groups", {})
    script_contents = state.get("script_contents", {})
    script_reused_map = state.get("script_reused", {})
    
    failed_any = False
    error_messages = []
    
    for sig in os_groups.keys():
        if script_reused_map.get(sig, False):
            continue
            
        script_content = script_contents.get(sig)
        if not script_content:
            failed_any = True
            error = f"[{sig}] Missing script content to validate."
            broadcast_log(job_id, agent_name, error, "error")
            error_messages.append(error)
            continue
            
        script_type = state.get("current_script_type", {}).get(sig, ".sh")
        
        # Check for bash syntax errors if it's a bash script
        if script_type == ".sh":
            fd, temp_path = tempfile.mkstemp(suffix=".sh")
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(script_content)
                
                # Run bash -n
                result = subprocess.run(["bash", "-n", temp_path], capture_output=True, text=True)
                if result.returncode != 0:
                    failed_any = True
                    error = f"[{sig}] Bash syntax validation failed: {result.stderr.strip()}"
                    broadcast_log(job_id, agent_name, error, "error")
                    error_messages.append(error)
                    continue
                    
                broadcast_log(job_id, agent_name, f"[{sig}] Bash syntax validation passed.")
            except Exception as e:
                broadcast_log(job_id, agent_name, f"[{sig}] Error running syntax check: {e}", "warning")
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                    
        # Check for catastrophic removals
        if "rm -rf / " in script_content or "rm -rf /*" in script_content:
            failed_any = True
            error = f"[{sig}] Script contains destructive root removal."
            broadcast_log(job_id, agent_name, error, "error")
            error_messages.append(error)
            
    if failed_any:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {"status": "FAILED", "error_message": "; ".join(error_messages)}
        
    broadcast_log(job_id, agent_name, "Script validation passed successfully.")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return {"current_stage": "SCRIPT_VALIDATED"}
