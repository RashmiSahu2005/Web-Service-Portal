import os
import tempfile
import json
import asyncio
import re
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def _generate_state_check_script(strategy: dict, os_family: str) -> str:
    installed_cmd = json.dumps(strategy.get("installed_version_command", []))
    
    return f"""#!/usr/bin/env python3
import subprocess
import json
import sys
import re

def extract_version(raw):
    if not raw: return None
    match = re.search(r"(\\d+\\.\\d+(?:\\.\\d+)*)", raw)
    if match: return match.group(1)
    return raw.strip()[:100]

def check():
    result = {{"installed_raw": None}}
    
    installed_cmd = {installed_cmd}
    if installed_cmd:
        try:
            res = subprocess.run(installed_cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                result["installed_raw"] = extract_version(res.stdout.strip())
        except Exception:
            pass
            
    print(json.dumps(result))

if __name__ == "__main__":
    check()
"""

def _upload_state_check_script(content: str, job_id: str, agent_name: str) -> str:
    fd, temp_path = tempfile.mkstemp(prefix="apphub_state_check_", suffix=".py")
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
            
        response = FleetDMService.upload_script(temp_path)
        if not response:
            return None
            
        script_data = response.get("script", {})
        script_id = script_data.get("id") or response.get("id") or response.get("script_id")
        if not script_id:
            return None
        return str(script_id)
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error uploading state check script: {e}", "error")
        return None
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

async def _check_on_host(host_id: int, script_id: str, job_id: str, agent_name: str) -> dict:
    try:
        run_response = FleetDMService.run_script(host_id, script_id)
        if not run_response:
            return {"installed": None}
            
        exec_id = run_response.get("execution_id")
        if not exec_id:
            return {"installed": None}
            
        max_attempts = 12
        attempts = 0
        
        while attempts < max_attempts:
            await asyncio.sleep(settings.POLLING_INTERVAL)
            result = FleetDMService.get_script_result(exec_id)
            if not result:
                return {"installed": None}
                
            exit_code = result.get("exit_code")
            if exit_code is not None or result.get("host_timeout"):
                if exit_code == 0:
                    output = result.get("output", "")
                    try:
                        parsed_json = json.loads(output)
                        return {
                            "installed": parsed_json.get("installed_raw")
                        }
                    except Exception as e:
                        broadcast_log(job_id, agent_name, f"Failed to parse state JSON on host {host_id}: {e}", "warning")
                        return {"installed": None}
                return {"installed": None}
            
            attempts += 1
            
        broadcast_log(job_id, agent_name, f"State check script timed out on host {host_id}", "warning")
        return {"installed": None}
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error checking state on host {host_id}: {e}", "error")
        return {"installed": None}

def _get_os_family(os_name: str) -> str:
    if os_name in ["Ubuntu", "Debian", "Linux"]:
        return "Linux"
    if os_name == "Windows":
        return "Windows"
    if os_name == "macOS":
        return "macOS"
    return "Linux"

async def check_application_state(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationStateCheckAgent"
    stage_name = "APPLICATION_STATE_CHECK"
    
    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}
        
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting generic application state check")
    
    updates = {
        "application_states": {},
        "installed_versions": {},
        "hosts_requiring_installation": []
    }
    
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK"]:
        broadcast_log(job_id, agent_name, f"Skipping state check because installation status is {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates
        
    app_name = state.get("application_name")
    os_groups = state.get("os_groups", {})
    strategies = state.get("strategies", {})
    
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Mocking state check for all hosts")
        for sig, host_ids in os_groups.items():
            for host_id in host_ids:
                updates["application_states"][host_id] = "NOT_INSTALLED"
                updates["installed_versions"][host_id] = None
                updates["hosts_requiring_installation"].append(host_id)
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    for sig, host_ids in os_groups.items():
        strategy = strategies.get(sig)
        if not strategy:
            broadcast_log(job_id, agent_name, f"No strategy found for {sig}, skipping.", "warning")
            for host_id in host_ids:
                updates["application_states"][host_id] = "CHECK_FAILED"
            continue
            
        os_family = _get_os_family(sig.split("_")[0])
        script_content = _generate_state_check_script(strategy, os_family)
        script_id = _upload_state_check_script(script_content, job_id, agent_name)
        
        if not script_id:
            broadcast_log(job_id, agent_name, f"Failed to upload state check script for {sig}.", "warning")
            for host_id in host_ids:
                updates["application_states"][host_id] = "CHECK_FAILED"
            continue
            
        for host_id in host_ids:
            broadcast_log(job_id, agent_name, f"Checking state on host {host_id} ({sig})...")
            res = await _check_on_host(host_id, script_id, job_id, agent_name)
            
            installed = res.get("installed")
            updates["installed_versions"][host_id] = installed
            broadcast_log(job_id, agent_name, f"Installed version: {installed or 'None'}")
            
            app_state = "UNKNOWN"
            if not installed:
                app_state = "NOT_INSTALLED"
            else:
                app_state = "INSTALLED"
                
            updates["application_states"][host_id] = app_state

    # We do not broadcast application state updates here, because Version Decision Node will do it
    # after determining the latest version.
    
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
