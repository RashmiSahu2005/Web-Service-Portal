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

def _generate_state_check_script(app_strategies: dict, is_windows: bool = False) -> str:
    # app_strategies is {app_name: strategy}
    if not is_windows:
        script = ['echo "{"']
        items = list(app_strategies.items())
        for i, (app_name, strategy) in enumerate(items):
            cmd = strategy.get("installed_version_command", [])
            comma = "," if i < len(items) - 1 else ""
            if not cmd:
                script.append(f'  echo \'  "{app_name}": {{"installed_raw": null}}{comma}\'')
            else:
                cmd_str = " ".join(cmd)
                script.append(f"""
  RAW=$( ({cmd_str}) 2>/dev/null )
  EC=$?
  if [ $EC -eq 0 ] && [ -n "$RAW" ]; then
    VERSION=$(echo "$RAW" | grep -oE '[0-9]+\\.[0-9]+(\\.[0-9]+)*' | head -n1)
    if [ -z "$VERSION" ]; then
      VERSION=$(echo "$RAW" | head -n1 | cut -c1-100 | tr -d '"' | tr -d "'")
    fi
    echo '  "{app_name}": {{"installed_raw": "'"$VERSION"'", "exit_code": 0}}{comma}'
  else
    # Escaping JSON correctly for null and integer
    if [ $EC -eq 0 ]; then
      echo '  "{app_name}": {{"installed_raw": null, "exit_code": 0}}{comma}'
    else
      echo '  "{app_name}": {{"installed_raw": null, "exit_code": '"$EC"'}}{comma}'
    fi
  fi
""")
        script.append('echo "}"')
        return "\n".join(script)

    checks = {}
    for app_name, strategy in app_strategies.items():
        checks[app_name] = strategy.get("installed_version_command", [])
        
    checks_json = json.dumps(checks)
    
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
    result = {{}}
    checks = {checks_json}
    
    for app_name, installed_cmd in checks.items():
        result[app_name] = {{"installed_raw": None, "exit_code": -1}}
        if installed_cmd:
            try:
                res = subprocess.run(installed_cmd, capture_output=True, text=True, timeout=10)
                result[app_name]["exit_code"] = res.returncode
                if res.returncode == 0:
                    result[app_name]["installed_raw"] = extract_version(res.stdout.strip())
            except Exception:
                pass
            
    print(json.dumps(result))

if __name__ == "__main__":
    check()
"""

def _upload_state_check_script(content: str, job_id: str, agent_name: str, ext: str = ".sh") -> str:
    fd, temp_path = tempfile.mkstemp(prefix="apphub_state_check_", suffix=ext)
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
                        # parsed_json is {app_name: {"installed_raw": "..."}}
                        return parsed_json
                    except Exception as e:
                        broadcast_log(job_id, agent_name, f"Failed to parse state JSON on host {host_id}: {e}", "warning")
                        return {}
                return {}
            
            attempts += 1
            
        broadcast_log(job_id, agent_name, f"State check script timed out on host {host_id}", "warning")
        return {}
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error checking state on host {host_id}: {e}", "error")
        return {}

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
        
    applications = state.get("applications", [])
    os_groups = state.get("os_groups", {})
    strategies = state.get("strategies", {})
    
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Mocking state check for all hosts")
        for sig, host_ids in os_groups.items():
            for host_id in host_ids:
                updates["application_states"][host_id] = {}
                updates["installed_versions"][host_id] = {}
                updates["hosts_requiring_installation"].append(host_id)
                for app in applications:
                    app_name = app.get("name") or app.get("application_name")
                    updates["application_states"][host_id][app_name] = "NOT_INSTALLED"
                    updates["installed_versions"][host_id][app_name] = None
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    for sig, host_ids in os_groups.items():
        app_strategies = strategies.get(sig, {})
        if not app_strategies:
            broadcast_log(job_id, agent_name, f"No strategy found for {sig}, skipping.", "warning")
            for host_id in host_ids:
                if host_id not in updates["application_states"]: updates["application_states"][host_id] = {}
                for app in applications:
                    app_name = app.get("name") or app.get("application_name")
                    # Do not overwrite successful states
                    if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                        updates["application_states"][host_id][app_name] = "STATE_CHECK_UNAVAILABLE"
            continue
            
        is_windows = "windows" in sig.lower()
        ext = ".py" if is_windows else ".sh"
        script_content = _generate_state_check_script(app_strategies, is_windows=is_windows)
        script_id = _upload_state_check_script(script_content, job_id, agent_name, ext=ext)
        
        if not script_id:
            broadcast_log(job_id, agent_name, f"Failed to upload state check script for {sig}.", "warning")
            for host_id in host_ids:
                if host_id not in updates["application_states"]: updates["application_states"][host_id] = {}
                for app in applications:
                    app_name = app.get("name") or app.get("application_name")
                    if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                        updates["application_states"][host_id][app_name] = "STATE_CHECK_UNAVAILABLE"
            continue
            
        for host_id in host_ids:
            broadcast_log(job_id, agent_name, f"Checking state on host {host_id} ({sig})...")
            # res is {app_name: {"installed_raw": "..."}}
            res = await _check_on_host(host_id, script_id, job_id, agent_name)
            
            if host_id not in updates["installed_versions"]: updates["installed_versions"][host_id] = {}
            if host_id not in updates["application_states"]: updates["application_states"][host_id] = {}
            
            active_app_name = state.get("application_name")
            for app in applications:
                app_name = app.get("name") or app.get("application_name")
                if app_name != active_app_name:
                    continue
                    
                app_res = res.get(app_name, {})
                installed = app_res.get("installed_raw")
                exit_code = app_res.get("exit_code", -1)
                
                updates["installed_versions"][host_id][app_name] = installed
                broadcast_log(job_id, agent_name, f"[{app_name}] Installed version: {installed or 'None'} (Exit Code: {exit_code})")
                
                app_state = "STATE_CHECK_UNAVAILABLE"
                if not res: # FleetDM execution failed entirely
                    app_state = "STATE_CHECK_UNAVAILABLE"
                elif installed:
                    app_state = "INSTALLED"
                elif exit_code == 0:
                    # The command succeeded but returned no version output
                    app_state = "CURRENT_VERSION_UNKNOWN"
                else:
                    app_state = "NOT_INSTALLED"
                    
                # Do not overwrite if already SUCCESS from a previous run or iteration
                if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                    updates["application_states"][host_id][app_name] = app_state
                
                if app_state in ["NOT_INSTALLED", "STATE_CHECK_UNAVAILABLE", "CURRENT_VERSION_UNKNOWN"] and host_id not in updates["hosts_requiring_installation"]:
                    updates["hosts_requiring_installation"].append(host_id)
                    
        # Cleanup the temporary state check script from FleetDM
        if script_id:
            try:
                FleetDMService.delete_script(int(script_id))
                broadcast_log(job_id, agent_name, f"Cleaned up temporary state check script {script_id}")
            except Exception as e:
                broadcast_log(job_id, agent_name, f"Failed to clean up state check script {script_id}: {e}", "warning")

    # We do not broadcast application state updates here, because Version Decision Node will do it
    # after determining the latest version.
    
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
