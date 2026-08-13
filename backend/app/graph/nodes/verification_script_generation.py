import hashlib
import re
import tempfile
import os
import subprocess
from app.graph.state import InstallationState
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.core.config import settings

def _build_verification_prompt(state: InstallationState, sig: str) -> str:
    parts = sig.split("_")
    os_name = parts[0]
    arch = parts[-1]
    
    strategy = state.get("strategies", {}).get(sig)
    verification_command = strategy.get('verification_command', []) if strategy else []
    
    script_type = ".ps1" if os_name == "Windows" else ".py"
    lang_name = "PowerShell" if script_type == ".ps1" else "Python 3"
    
    prompt = f"""You are a senior system administrator. Generate a robust, idempotent {lang_name} script for {os_name} on {arch} architecture.
        
DO NOT wrap your response in any conversational text. Return ONLY the {lang_name} script inside ```{lang_name.lower().replace(" 3", "")} fences.

Application: {state.get('application_name')}
Version: {state.get('version')}
OS: {os_name}
Architecture: {arch}

REQUIREMENTS:
"""
    if script_type == ".ps1":
        prompt += f"""- The script MUST be a native PowerShell script.
- It MUST be non-interactive (no prompts).
- **CRITICAL**: Do NOT run indefinitely. Ensure commands do not hang.
- Capture stdout and stderr from all commands and print them.
- Do NOT use `sudo`. Assume the script is already running as Administrator/SYSTEM.
- This script is EXCLUSIVELY for VERIFYING the installation of the application. DO NOT include installation logic.
- Verify the application is installed successfully and the correct version is present if possible (e.g., check Registry HKLM:\\Software or Program Files).
- CRITICAL for Windows: Do NOT use `winget` or any interactive package manager for verification, as they often hang indefinitely in a SYSTEM context. Check the Registry (e.g., `HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall`) or file paths (e.g. `C:\\Program Files`) directly.
- Print the verification output and exit with 0 on success, or a non-zero exit code on failure (e.g., `exit 1`).
"""
    else:
        prompt += f"""- The script MUST be Python 3 compatible.
- The script MUST begin with #!/usr/bin/env python3.
- It MUST be non-interactive (no prompts).
- Use the `subprocess` module for running OS commands. Avoid `shell=True` unless absolutely necessary.
- **CRITICAL**: Enforce a strict timeout of {settings.VERIFICATION_COMMAND_TIMEOUT} seconds on all `subprocess.run` calls (e.g. `subprocess.run(..., timeout={settings.VERIFICATION_COMMAND_TIMEOUT})`).
- Catch `subprocess.TimeoutExpired`, log the timeout, print whatever stdout/stderr was captured so far, and exit with a non-zero exit code. Never allow the verification script to hang indefinitely.
- Capture stdout and stderr from all subprocesses and print them.
- Do NOT use `sudo`. Assume the script is already running as root or Administrator/SYSTEM.
- This script is EXCLUSIVELY for VERIFYING the installation of the application. DO NOT include installation logic.
- Verify the application is installed successfully and the correct version is present if possible.
- IMPORTANT: Since this script runs via an MDM agent as root, standard user $PATH variables might not be loaded. Do NOT rely blindly on just the command name. Actively try to locate the binary in common installation paths (e.g. `/usr/bin/`, `/opt/`, `/usr/local/bin/`, `/snap/bin/`, `C:\\Program Files\\`, etc.) and attempt verification using the absolute path before deciding it failed.
- Print the verification output and exit with 0 on success, or a non-zero exit code on failure.
"""
    if verification_command:
        prompt += f"\nCRITICAL INSTRUCTION:\nUse the following exact verification command(s) as a primary method for verification:\n{verification_command}\n"
    
    return prompt

def _extract_and_validate_script(raw_response: str, job_id: str, agent_name: str, sig: str) -> tuple[str, str]:
    script = raw_response
    os_name = sig.split("_")[0]
    script_type = ".ps1" if os_name == "Windows" else ".py"
    
    match = re.search(r"```(?:python|powershell)?\n(.*?)```", raw_response, re.DOTALL | re.IGNORECASE)
    if match:
        script = match.group(1).strip()
        
    script = script.strip()
    
    if not script:
        return "", "Extracted script is empty."
        
    if script_type == ".py":
        if not script.startswith("#!/usr/bin/env python3") and "import " not in script:
            return "", "Response does not appear to be a valid Python script. Missing shebang or imports."
            
        fd, temp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(script)
                
            result = subprocess.run(["python3", "-m", "py_compile", temp_path], capture_output=True, text=True)
            if result.returncode != 0:
                return "", f"Python syntax validation failed: {result.stderr}"
                
            broadcast_log(job_id, agent_name, "Python syntax validation passed.")
        except Exception as e:
            return "", f"Failed to run python syntax validation: {e}"
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
    else:
        broadcast_log(job_id, agent_name, "Skipping syntax validation for PowerShell verification script.")
            
    return script, ""

def verification_script_generation(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "VerificationScriptGenerationAgent"
    stage_name = "VERIFICATION_SCRIPT_GENERATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, f"Generating verification script for {state.get('application_name')}")
    
    updates = {
        "verification_script_contents": state.get("verification_script_contents", {})
    }
    
    # If the state status is already FAILED, skip generating verification script
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK", "CANCELLED"]:
        broadcast_log(job_id, agent_name, f"Skipping verification script generation because status is {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    os_groups = state.get("os_groups", {})
    max_retries = 3
    failed_any = False
    error_msgs = []
    
    for sig in os_groups.keys():
        broadcast_log(job_id, agent_name, f"Generating verification script for {sig}")
        
        base_prompt = _build_verification_prompt(state, sig)
        current_prompt = base_prompt
        
        success = False
        
        for attempt in range(max_retries):
            broadcast_log(job_id, agent_name, f"Calling LLMService for {sig} (Attempt {attempt + 1}/{max_retries})")
            
            try:
                llm_response = LLMService.generate(current_prompt)
                if not llm_response:
                    error_message = f"Received empty response from LLMService for {sig}."
                    broadcast_log(job_id, agent_name, error_message, "error")
                    if attempt == max_retries - 1:
                        error_msgs.append(error_message)
                        failed_any = True
                    continue
                    
                script_content, error = _extract_and_validate_script(llm_response, job_id, agent_name, sig)
                if not script_content:
                    broadcast_log(job_id, agent_name, error, "error")
                    if attempt < max_retries - 1:
                        broadcast_log(job_id, agent_name, "Retrying generation with error feedback...")
                        current_prompt = base_prompt + f"\n\nYOUR PREVIOUS RESPONSE FAILED VALIDATION WITH THIS ERROR:\n{error}\n\nPlease fix the error."
                        continue
                    else:
                        error_msgs.append(f"Failed to generate valid script for {sig}: {error}")
                        failed_any = True
                        break
                    
                broadcast_log(job_id, agent_name, f"Verification script generated successfully for {sig}")
                
                updates["verification_script_contents"][sig] = script_content
                success = True
                break
                
            except Exception as e:
                error_message = f"Error during verification generation for {sig}: {e}"
                broadcast_log(job_id, agent_name, error_message, "error")
                if attempt == max_retries - 1:
                    error_msgs.append(error_message)
                    failed_any = True
                    
        if not success:
            failed_any = True

    if failed_any:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": "; ".join(error_msgs)}
        
    updates["current_stage"] = "VERIFICATION_SCRIPT_GENERATED"
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
