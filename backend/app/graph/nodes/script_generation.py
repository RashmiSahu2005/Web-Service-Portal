import hashlib
import re
import tempfile
import os
import subprocess
from app.graph.state import InstallationState
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.core.config import settings

def _build_prompt(state: InstallationState, sig: str, script_type: str = ".py", failure_context: list = None) -> str:
    parts = sig.split("_")
    os_name = parts[0]
    arch = parts[-1]
    
    strategy = state.get("strategies", {}).get(sig)
    strategy_info = ""
    if strategy:
        strategy_info = f"""
STRATEGY DETAILS:
Package Manager: {strategy.get('package_manager', 'N/A')}
Package Name: {strategy.get('package_name', 'N/A')}
Installation Method: {strategy.get('installation_method', 'N/A')}
"""

    if script_type != ".py":
        script_lang = "Bash (.sh)" if script_type == ".sh" else "PowerShell (.ps1)"
        prompt = f"""You are a senior system administrator. Generate a robust, idempotent {script_lang} script for {os_name} on {arch} architecture.
        
DO NOT wrap your response in any conversational text. Return ONLY the {script_lang} script inside ```{script_type.replace('.', '')} fences.

Application: {state.get('application_name')}
Version: {state.get('version')}
OS: {os_name}
Architecture: {arch}
Description: {state.get('description')}
{strategy_info}

REQUIREMENTS:
- The script MUST be non-interactive (no prompts).
- It MUST be idempotent (safe to run multiple times).
- It MUST handle errors gracefully and exit with a non-zero exit code on failure, and 0 on success.
- Do NOT use `sudo`. Assume the script is already running as root or Administrator/SYSTEM.
- If Version is 'Latest', your script MUST install the newest available version from the official package repository.
- If Version is an exact version number, ensure that specific version is installed.
- Idempotency: Before installing, explicitly check if the requested version (or any version if 'Latest') is already installed. If it is already installed and satisfies the requirement, print a success message and exit with code 0 immediately without running the installer.
- Do NOT include any secrets or hardcoded credentials.
- Do NOT include destructive commands like `rm -rf /` or recursive deletions of sensitive directories.
- Add clear stdout/stderr logging for installation progress.
"""
    else:
        prompt = f"""You are a senior system administrator. Generate a robust, idempotent Python 3 script for {os_name} on {arch} architecture.
            
DO NOT wrap your response in any conversational text. Return ONLY the Python script inside ```python fences.

Application: {state.get('application_name')}
Version: {state.get('version')}
OS: {os_name}
Architecture: {arch}
Description: {state.get('description')}
{strategy_info}

REQUIREMENTS:
- The script MUST be Python 3 compatible.
- The script MUST begin with #!/usr/bin/env python3.
- It MUST be non-interactive (no prompts).
- It MUST be idempotent (safe to run multiple times).
- It MUST handle errors gracefully and exit with a non-zero exit code on failure, and 0 on success.
- Use the `subprocess` module for running OS commands. Avoid `shell=True` unless absolutely necessary.
- **CRITICAL**: Enforce a strict timeout of {settings.INSTALL_COMMAND_TIMEOUT} seconds on all `subprocess.run` calls (e.g. `subprocess.run(..., timeout={settings.INSTALL_COMMAND_TIMEOUT})`).
- Catch `subprocess.TimeoutExpired`, log the timeout, print whatever stdout/stderr was captured so far, and exit with a non-zero exit code. Never allow the script to hang indefinitely.
- Capture stdout and stderr from all subprocesses and print them so they are returned in the script's output log.
- Do NOT use `sudo`. Assume the script is already running as root or Administrator/SYSTEM.
- If the OS is Linux (Ubuntu/Debian), prefer official APT repositories. Use `.deb` packages when a repository is not appropriate. Set `DEBIAN_FRONTEND=noninteractive`.
- If the OS is Windows, prefer `.exe` installers, MSI, or PowerShell package managers (like winget).
- **Windows SYSTEM Context**: If using `winget` or another package manager on Windows, first verify it is accessible and usable in the current SYSTEM/non-interactive context (e.g. run `winget --version`). If it is unavailable or hangs, detect this explicitly, return a clear failure message, and exit with a non-zero code. Do not hang.
- If Version is 'Latest', your script MUST install the newest available version from the official package repository.
- If Version is an exact version number, ensure that specific version is installed.
- **Idempotency**: Before installing, explicitly check if the requested version (or any version if 'Latest') is already installed. If it is already installed and satisfies the requirement, print a success message and exit with code 0 immediately without running the installer.
- Do NOT include any secrets or hardcoded credentials.
- Do NOT include destructive commands like `rm -rf /` or recursive deletions of sensitive directories.
- Add clear stdout/stderr logging for installation progress.
"""

    install_command = state.get("install_command")
    if install_command:
        prompt += f"\nCRITICAL INSTRUCTION:\nUse the following exact installation command as the core of your script. It is the officially tested and verified command for this application:\n{install_command}\n"
    
    if failure_context:
        prompt += "\nPREVIOUS ATTEMPT FAILURE CONTEXT\n\nThis is a retry of a previously failed installation.\n\n"
        for ctx in failure_context:
            prompt += f"Previous attempt: {ctx.get('attempt')}\n"
            prompt += f"Previous script type: {ctx.get('failed_script_type')}\n"
            prompt += f"Previous exit code: {ctx.get('exit_code')}\n"
            prompt += f"Previous execution output:\n{ctx.get('error_output', '')[-1500:]}\n"
            prompt += f"Failure analysis:\n{ctx.get('analysis')}\n\n"
            
        prompt += """Requirements for this retry:
1. Analyze the previous failure before generating the script.
2. Identify the likely root cause.
3. Do not repeat the failed command or execution mechanism when the error indicates that the mechanism itself is unavailable or problematic.
4. Generate a corrected script that specifically addresses the failure.
5. Keep the script non-interactive and idempotent.
6. Preserve the application's intended installation goal.
7. Do not invent credentials, secrets, or unsupported dependencies.
8. If the previous approach is incompatible with the target OS or execution context, use a different compatible approach.
"""

    return prompt

def _extract_and_validate_script(raw_response: str, job_id: str, agent_name: str, script_type: str = ".py") -> tuple[str, str]:
    script = raw_response
    
    match = re.search(r"```(?:python|bash|sh|powershell|ps1)?\n(.*?)```", raw_response, re.DOTALL | re.IGNORECASE)
    if match:
        script = match.group(1).strip()
        
    script = script.strip()
    
    if not script:
        return "", "Extracted script is empty."
        
    sensitive_keywords = ["AWS_ACCESS_KEY_ID", "PASSWORD=", "SECRET_KEY"]
    for keyword in sensitive_keywords:
        if keyword in script.upper():
            return "", f"Generated script contains potential secret ({keyword}). Rejecting."
            
    if script_type == ".py":
        if not script.startswith("#!/usr/bin/env python3") and "import " not in script:
            return "", "Response does not appear to be a valid Python script. Missing shebang or imports."
            
        if "bash" in script.lower() and "apt-get" in script and "def " not in script:
            broadcast_log(job_id, agent_name, "Response looks like a Bash script instead of a Python script.", "warning")
            
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
        broadcast_log(job_id, agent_name, f"Non-Python script type ({script_type}) generated. Skipping Python syntax validation.")

    return script, ""

def generate_script(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptGenerationAgent"
    stage_name = "SCRIPT_GENERATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, f"Starting script generation for Application: {state.get('application_name')}")
    
    updates = {
        "current_stage": "SCRIPT_GENERATED",
        "script_contents": state.get("script_contents", {}),
        "script_hashes": state.get("script_hashes", {}),
        "current_attempts": state.get("current_attempts", {}),
        "maximum_attempts": state.get("maximum_attempts", {}),
        "current_script_type": state.get("current_script_type", {})
    }
    
    os_groups = state.get("os_groups", {})
    script_reused = state.get("script_reused", {})
    
    max_retries = 3
    failed_any = False
    error_msgs = []
    
    for sig in os_groups.keys():
        if script_reused.get(sig):
            broadcast_log(job_id, agent_name, f"Skipping generation for {sig} (script reused)")
            continue
            
        os_name, arch = sig.split("_")[:2] if len(sig.split("_")) == 2 else (sig.split("_")[0], sig.split("_")[-1])
        
        # Initialize attempt mapping if not set
        if sig not in updates["current_attempts"]:
            updates["current_attempts"][sig] = 1
            
        current_attempt = updates["current_attempts"][sig]
        
        # OS-specific attempt and script type logic
        if "windows" in os_name.lower():
            updates["maximum_attempts"][sig] = 3
            if current_attempt in [1, 2]:
                script_type = ".ps1"
            else:
                script_type = ".py"
        else:
            updates["maximum_attempts"][sig] = 3
            if current_attempt in [1, 2]:
                script_type = ".py"
            else:
                script_type = ".sh"
            
        updates["current_script_type"][sig] = script_type
        
        broadcast_log(job_id, agent_name, f"Generating {script_type} script for {sig} (Attempt {current_attempt}/{updates['maximum_attempts'][sig]})")
            
        failure_context = state.get("script_failure_context", {}).get(sig)
        base_prompt = _build_prompt(state, sig, script_type, failure_context)
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
                    
                script_content, error = _extract_and_validate_script(llm_response, job_id, agent_name, script_type)
                if not script_content:
                    broadcast_log(job_id, agent_name, error, "error")
                    if attempt < max_retries - 1:
                        broadcast_log(job_id, agent_name, "Retrying script generation with error feedback...")
                        current_prompt = base_prompt + f"\n\nYOUR PREVIOUS RESPONSE FAILED VALIDATION WITH THIS ERROR:\n{error}\n\nPlease fix the error and provide the corrected script."
                        continue
                    else:
                        error_msgs.append(f"Failed to generate valid script for {sig}: {error}")
                        failed_any = True
                        break
                    
                script_hash = hashlib.sha256(script_content.encode('utf-8')).hexdigest()
                
                broadcast_log(job_id, agent_name, f"Script generated successfully for {sig}")
                broadcast_log(job_id, agent_name, f"Script SHA256: {script_hash}")
                
                updates["script_contents"][sig] = script_content
                updates["script_hashes"][sig] = script_hash
                success = True
                break
                
            except Exception as e:
                error_message = f"Error during script generation for {sig}: {e}"
                broadcast_log(job_id, agent_name, error_message, "error")
                if attempt == max_retries - 1:
                    error_msgs.append(error_message)
                    failed_any = True
                    
        if not success:
            failed_any = True

    if failed_any:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": "; ".join(error_msgs)}
        
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
