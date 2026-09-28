import hashlib
import re
import tempfile
import os
import subprocess
from app.graph.state import InstallationState
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.core.config import settings
import time

# ── OS-AWARE SCRIPT TYPE SELECTION ───────────────────────────────────────────
# Determines the preferred script type based on the OS signature and attempt number.
# Strategy:
#   Linux/macOS (and any non-Windows OS):  Attempt 1 → .sh, Attempt 2 → .sh, Attempt 3 → .py
#   Windows:                               Attempt 1 → .ps1, Attempt 2 → .ps1, Attempt 3 → .py
#
# The OS is inferred from the sig (e.g. "Ubuntu_amd64", "Windows_amd64", "macOS_arm64").
# Do NOT hardcode specific OS names beyond the Windows/non-Windows distinction.

def _get_script_type_for_attempt(sig: str, attempt: int) -> str:
    """Return the preferred script extension for a given OS signature and attempt number."""
    os_name = sig.split("_")[0].lower()
    is_windows = "windows" in os_name or "win" == os_name
    
    if is_windows:
        # ALWAYS use PowerShell (.ps1) for Windows. Do NOT fallback to Python.
        return ".ps1"
    else:
        # ALWAYS use Bash (.sh) for Linux/macOS. Do NOT fallback to Python.
        return ".sh"

# ── PROMPT BUILDER ────────────────────────────────────────────────────────────

def _build_prompt(state: InstallationState, sig: str, script_type: str = ".sh", failure_context: list = None) -> str:
    parts = sig.split("_")
    os_name = parts[0]
    arch = parts[-1]
    
    app_name = state.get("application_name")
    target_version = state.get("target_version", "latest")
    strategy = state.get("strategies", {}).get(sig, {}).get(app_name)

    app_info = f"Target: {app_name} (Version: {target_version})\n"
    if strategy:
        pkg_mgr = strategy.get("package_manager") or ""
        if pkg_mgr:
            app_info += f"Package Manager: {pkg_mgr}\n"

        pkg_name = strategy.get("package_name") or ""
        if pkg_name:
            app_info += f"Package Name: {pkg_name}\n"

        method = strategy.get("recommended_method") or strategy.get("install_method") or ""
        if method:
            app_info += f"Installation Method: {method}\n"

        repo = strategy.get("repository") or ""
        if repo:
            app_info += f"Repository: {repo}\n"

        repo_url = strategy.get("repository_url") or ""
        if repo_url:
            app_info += f"Repository URL: {repo_url}\n"
            
        artifact_url = strategy.get("artifact_url") or ""
        if artifact_url:
            app_info += f"Artifact URL: {artifact_url}\n"

        install_cmd = strategy.get("installation_command") or strategy.get("install_command") or ""
        if install_cmd:
            app_info += f"Installation Command: {install_cmd}\n"

        deps = strategy.get("dependencies") or []
        if deps:
            app_info += f"Required Dependencies (check if installed first, ONLY install if missing to save time):\n"
            for dep in deps:
                app_info += f"  - {dep}\n"

        verify_method = strategy.get("verification_method") or ""
        if verify_method:
            app_info += f"Verification Method: {verify_method}\n"

        verify_cmd = strategy.get("verification_command") or ""
        if verify_cmd:
            app_info += f"Verification Command: {verify_cmd}\n"

        installed_cmd = strategy.get("installed_version_command") or []
        if installed_cmd:
            cmd_str = " ".join(installed_cmd)
            app_info += f"State Check Command: {cmd_str}\n"
            app_info += f"CRITICAL: The system uses the above State Check Command to detect if the app is installed. Your installation script MUST install the app in a way that allows this exact command to succeed (e.g. if it uses 'snap list', you MUST use 'snap install').\n"

        exec_path = strategy.get("executable_path") or ""
        if exec_path:
            app_info += f"Executable Path: {exec_path}\n"

        notes = strategy.get("notes") or []
        for n in notes:
            app_info += f"NOTE: {n}\n"

        sources = strategy.get("source_urls") or []
        if sources:
            app_info += f"Sources: {', '.join(sources[:3])}\n"

    if script_type == ".sh":
        prompt = f"""Generate a robust, idempotent Bash (.sh) installation script for {os_name} ({arch}).

Return ONLY the script inside ```sh fences. No explanations.
The script MUST begin with exactly: `#!/bin/bash`

You must install:
{app_info}

Constraints:
1. Non-interactive (no prompts). Use DEBIAN_FRONTEND=noninteractive for apt.
2. Idempotent: Exit 0 if already installed and version matches.
3. Exit non-zero on installation failure.
4. No sudo (assume running as root).
5. Prefer official package repositories. Avoid deprecated apt-key; use signed-by keyring.
6. Print progress to stdout.
7. CRITICAL APT HANDLING: Do NOT use a blanket `apt-get update -y || true` and do NOT swallow network failures.
   - First, check if the package is already available using `apt-cache policy <package>`. If a valid candidate exists, skip `apt-get update` to avoid unrelated repository errors.
   - If you MUST run `apt-get update`, capture the exit code and output (e.g. `apt-get update >"/var/tmp/apt_update.log" 2>&1; UPDATE_EXIT=$?`).
   - If it fails due to a network/DNS error, you MUST exit 1 and report `DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE` or `DNS_FAILURE`.
   - If it fails due to an unrelated broken third-party GPG repository (e.g., NO_PUBKEY), do not fail the installation if the target package can still be installed.
8. CRITICAL SAFETY: NEVER remove the old installation before validating the new one!
   - Detect current version.
   - Download new package (if applicable).
   - Validate download (e.g. `test -s`, `tar -tzf`, `dpkg-deb --info`, `rpm -qip`).
   - CRITICAL NOEXEC AND PERMISSION AVOIDANCE: Use `/var/tmp` or `/opt` for temporary files and downloads. Do NOT use `/tmp`.
9. DIRECT DEB INSTALLATION RULES (if strategy uses a direct download):
   - Download the exact artifact.
   - Verify it's a valid deb.
   - Use `dpkg-deb -f "$PACKAGE" Depends` to extract dependencies.
   - Do NOT blindly install LLM-guessed dependencies.
   - Validate that each dependency package actually exists for the target Ubuntu version/architecture before attempting to install it (e.g., using `apt-cache show`).
   - Install only the valid dependencies that are missing.
   - Install the .deb package.
10. TARBALL INSTALLATION RULES (if strategy uses a tarball):
   - Download, validate integrity, and extract to a controlled directory (e.g., `/opt/`).
   - Verify expected files exist and create symlinks if needed.
11. VERIFICATION: Installation and verification MUST remain in the SAME generated script. At the end of the script, run the explicit Verification Command provided (or a safe alternative if none provided). Exit 0 ONLY if verification succeeds.
12. UNIFIED RESULT OUTPUT: Any exit must print a structured DeployIQ result.
    If success (both installation and verification succeeded):
    DEPLOYIQ_RESULT_START
    APPLICATION={app_name}
    INSTALLATION_STATUS=SUCCESS
    VERIFICATION_STATUS=SUCCESS
    INSTALLED_VERSION=<actual version>
    DEPLOYIQ_RESULT_END
    exit 0

    If failure (any step failed):
    DEPLOYIQ_RESULT_START
    APPLICATION={app_name}
    INSTALLATION_STATUS=FAILED
    DEPLOYIQ_FAILURE_CATEGORY=<category>
    DEPLOYIQ_RESULT_END
    exit 1
    
    Valid Failure Categories: NETWORK_FAILURE, DNS_FAILURE, APT_REPOSITORY_FAILURE, APT_GPG_FAILURE, PACKAGE_NOT_FOUND, DEPENDENCY_FAILURE, PACKAGE_MANAGER_FAILURE, DOWNLOAD_FAILURE, VERSION_MISMATCH, PERMISSION_FAILURE, EXECUTION_TIMEOUT, VERIFICATION_FAILURE, SCRIPT_ERROR, ARTIFACT_REQUIRED.
13. PRIVATE PORTAL / MANUAL ARTIFACT: If the installation strategy indicates that the application requires a private vendor portal or manual download, DO NOT invent URLs. You MUST immediately exit 1 and output DEPLOYIQ_FAILURE_CATEGORY=ARTIFACT_REQUIRED.
14. EXACT STRATEGY ONLY: You MUST use the exact repository, download URL, artifact URL, and installation command provided. Do NOT invent URLs or package names.
    - CRITICAL URL RULE: NEVER construct a URL from a filename, guess a CDN hostname, or convert a generic download page into a package URL. Use ONLY the explicit URLs provided. If you cannot fulfill a direct artifact installation without guessing an unknown URL, you must write a script that echoes 'FATAL: Missing deterministic URL' and exits 1 with DEPLOYIQ_FAILURE_CATEGORY=ARTIFACT_REQUIRED.
    - REPOSITORY RULE: Never invent repository URLs or GPG key URLs. If a custom repository is required but exact URLs were not provided in the research, exit 1 with DEPLOYIQ_FAILURE_CATEGORY=APT_REPOSITORY_FAILURE.
"""
    elif script_type == ".ps1":
        prompt = f"""Generate a robust, idempotent PowerShell (.ps1) installation script for {os_name} ({arch}).

Return ONLY the script inside ```powershell fences. No explanations.

You must install:
{app_info}

Constraints:
1. Non-interactive. Use -Confirm:$false, -Force as appropriate.
2. Idempotent: Exit 0 if already installed and version matches.
3. Exit non-zero on installation failure.
4. No elevation prompts (assume running as SYSTEM/Admin).
5. Prefer winget, scoop, or official MSI. Verify winget is available before using it.
6. CRITICAL SAFETY: NEVER remove the old installation before validating the new one!
   - Download new package (if applicable)
   - Validate download (e.g. Test-Path, file size checks, signature checks)
   - Extract/install to temporary location if possible before overwriting.
7. After installation, verify the installation. Use the explicit Verification Command provided if available. Otherwise, use a safe method (e.g., Test-Path on the executable). Do NOT blindly run `<app> --version` as SYSTEM. If the verification fails, you MUST `exit 1`.
8. At the END of the script (only if BOTH installation and verification succeeded), print EXACTLY:
DEPLOYIQ_RESULT_START
APPLICATION={app_name}
INSTALLATION_STATUS=SUCCESS
VERIFICATION_STATUS=SUCCESS
INSTALLED_VERSION=<actual version>
DEPLOYIQ_RESULT_END
9. EXACT STRATEGY ONLY: You MUST use the exact repository, download URL, and installation command provided in the strategy. Do NOT invent, guess, or construct vendor download domains (e.g., example.com, yourdomain.com). If you cannot fulfill the installation without guessing an unknown URL, you must write a script that echoes 'FATAL: Missing deterministic URL' and exits 1.
9. Version check leniency: Verify the package installed and runs. Do NOT fail the installation solely because the OS package manager provides a slightly different or older version string than requested. Print SUCCESS if the package installs successfully.
"""
    else:  # .py — cross-platform fallback
        prompt = f"""Generate a robust Python 3 installation script for {os_name} ({arch}).

Return ONLY the Python script inside ```python fences. No explanations.

You must install:
{app_info}

Constraints:
1. Must begin with #!/usr/bin/env python3
2. Non-interactive (no prompts).
3. Idempotent: Exit 0 if already installed and version matches.
4. Exit non-zero if installation fails.
5. Use subprocess with timeout={settings.INSTALL_COMMAND_TIMEOUT}. Exit on TimeoutExpired.
6. Print all subprocess stdout/stderr.
7. No sudo (assume root/SYSTEM).
8. If Windows, verify package manager (winget) is available in SYSTEM context before using it.
9. CRITICAL SAFETY: NEVER remove the old installation before validating the new one!
   - Download new package (if applicable) and validate it (size, headers)
   - Extract/install to temporary location if possible before overwriting.
10. After installation, verify the installation. Use the explicit Verification Command provided if available. Otherwise, use a safe method (e.g., check if the executable exists). Do NOT blindly run `<app> --version` as root. If the verification fails, you MUST `sys.exit(1)`.
11. At the END of the script (only if BOTH installation and verification succeeded), print EXACTLY:
DEPLOYIQ_RESULT_START
APPLICATION={app_name}
INSTALLATION_STATUS=SUCCESS
VERIFICATION_STATUS=SUCCESS
INSTALLED_VERSION=<actual version>
DEPLOYIQ_RESULT_END
12. CRITICAL f-string safety: NEVER use f-strings for shell command strings that contain curly braces (e.g. dpkg format strings). Use plain strings or str.format() instead.
13. Version check leniency: Verify the package installed (returncode=0). Do NOT fail solely because the distro provides an older version. Print SUCCESS if the package installs and runs.
"""


    install_command = state.get("install_command")
    if install_command:
        prompt += f"\nCRITICAL INSTRUCTION:\nUse the following exact installation command:\n{install_command}\n"
    
    if failure_context:
        # Filter to non-zero attempt entries (exclude cached-script pre-execution failures)
        real_failures = [ctx for ctx in failure_context if ctx.get("attempt", 0) > 0]
        cache_failures = [ctx for ctx in failure_context if ctx.get("attempt", 0) == 0]
        
        prompt += "\n\n" + "="*60 + "\nPREVIOUS ATTEMPT FAILURES\n" + "="*60 + "\n"
        
        if cache_failures:
            prompt += "\nNOTE: A previously cached script was invalidated and could not be used:\n"
            for ctx in cache_failures:
                prompt += f"  Reason: {ctx.get('analysis', 'Unknown')}\n"
            prompt += "\n"
        
        if real_failures:
            prompt += (
                "CRITICAL: The following generation attempts FAILED. "
                "Do NOT repeat the same installation method, package source, "
                "repository configuration, download mechanism, or other known failing approach "
                "unless you have a specific technical reason why a different invocation will succeed.\n\n"
            )
            for ctx in real_failures:
                prompt += f"--- Attempt {ctx.get('attempt')} ({ctx.get('script_type', 'unknown')} script) ---\n"
                prompt += f"Exit Code: {ctx.get('exit_code', 'N/A')}\n"
                prompt += f"Failure Analysis: {ctx.get('analysis', 'No analysis available')}\n"
                error_output = ctx.get("error_output", "")
                if error_output:
                    # Trim to last 1500 chars to avoid overflowing the context
                    trimmed = error_output[-1500:]
                    prompt += f"Script Output (last 1500 chars):\n{trimmed}\n"
                prompt += "\n"
        
        prompt += (
            "Requirements for this attempt:\n"
            "1. Fix the exact errors described above using a DIFFERENT approach.\n"
            "2. If a repository/key/download failed, use a different source or method.\n"
            "3. Output ONLY the fixed script inside the appropriate fences.\n"
        )
        # NOTE: Web search evidence is now provided via the Installation Research Agent
        # (installation_research.py) which uses SearXNG and feeds results into
        # state['strategies'][sig][app_name] before script generation runs.
        # No additional inline web search is performed here.

    return prompt


def _extract_and_validate_script(raw_response: str, job_id: str, agent_name: str, script_type: str = ".sh") -> tuple[str, str]:
    script = raw_response
    
    # Extract from fenced code block
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
            
        fd, temp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(script)
                
            result = subprocess.run(["python3", "-m", "py_compile", temp_path], capture_output=True, text=True)
            if result.returncode != 0:
                stderr_text = result.stderr.strip()
                error_detail = stderr_text
                lineno_match = re.search(r'line (\d+)', stderr_text)
                if lineno_match:
                    bad_lineno = int(lineno_match.group(1))
                    lines = script.splitlines()
                    if 0 < bad_lineno <= len(lines):
                        bad_line = lines[bad_lineno - 1]
                        error_detail = f"{stderr_text}\nOffending line {bad_lineno}: {bad_line}"
                broadcast_log(job_id, agent_name, f"Python Syntax Error: {error_detail}", "error")
                return "", f"Python syntax validation failed: {error_detail}"
                
            broadcast_log(job_id, agent_name, "Python syntax validation passed.")
        except Exception as e:
            return "", f"Failed to run python syntax validation: {e}"
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass
    elif script_type == ".sh":
        # Strip any shebangs if the LLM included one anyway
        if script.startswith("#!"):
            script = "\n".join(script.splitlines()[1:]).strip()
        broadcast_log(job_id, agent_name, "Bash script accepted (shebang stripped if present to avoid noexec bug).")
    elif script_type == ".ps1":
        broadcast_log(job_id, agent_name, "PowerShell script accepted (no syntax pre-check applied).")

    return script, ""


def generate_script(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptGenerationAgent"
    stage_name = "SCRIPT_GENERATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    
    app_name = state.get("application_name", "Unknown")
    target_version = state.get("target_version", "latest")
    broadcast_log(job_id, agent_name, f"Starting script generation for Application: {app_name}")
    
    os_groups = state.get("os_groups", {})
    script_reused = state.get("script_reused", {})
    
    script_generation_start_time = state.get("script_generation_start_time")
    if not script_generation_start_time:
        script_generation_start_time = time.time()
        
    script_contents = state.get("script_contents", {})
    
    updates = {
        "current_stage": "SCRIPT_GENERATED",
        "script_contents": script_contents,
        "script_hashes": state.get("script_hashes", {}),
        "current_attempts": state.get("current_attempts", {}),
        "maximum_attempts": state.get("maximum_attempts", {}),
        "current_script_type": state.get("current_script_type", {}),
        "script_generation_start_time": script_generation_start_time
    }
    
    llm_retries = 3  # LLM call retries per attempt (for empty responses / syntax errors)
    failed_any = False
    error_msgs = []
    
    for sig in os_groups.keys():
        if script_reused.get(sig):
            broadcast_log(job_id, agent_name, f"[{sig}] Skipping generation (script reused from registry)")
            continue
        
        # ── Determine attempt number ──────────────────────────────────────────
        if sig not in updates["current_attempts"]:
            updates["current_attempts"][sig] = 1
        if sig not in updates["maximum_attempts"]:
            updates["maximum_attempts"][sig] = 3
            
        current_attempt = updates["current_attempts"][sig]
        max_attempts    = updates["maximum_attempts"][sig]
        
        # ── OS-aware script type ──────────────────────────────────────────────
        script_type = _get_script_type_for_attempt(sig, current_attempt)
        updates["current_script_type"][sig] = script_type
        
        broadcast_log(job_id, agent_name,
            f"[DeployIQ][ScriptGeneration] Application={app_name} Version={target_version} "
            f"OS={sig} Attempt={current_attempt}/{max_attempts} ScriptType={script_type}")
        
        failure_context = state.get("script_failure_context", {}).get(sig)
        base_prompt = _build_prompt(state, sig, script_type, failure_context)
        current_prompt = base_prompt
        
        success = False
        
        for llm_attempt in range(llm_retries):
            broadcast_log(job_id, agent_name,
                f"[{sig}] Calling LLM (inner attempt {llm_attempt + 1}/{llm_retries})...")
            
            try:
                llm_response = LLMService.generate(current_prompt)
                if not llm_response:
                    error_message = f"LLM returned empty response for {sig} (inner attempt {llm_attempt + 1})."
                    broadcast_log(job_id, agent_name, error_message, "error")
                    if llm_attempt == llm_retries - 1:
                        error_msgs.append(error_message)
                        failed_any = True
                    continue
                    
                script_content, error = _extract_and_validate_script(llm_response, job_id, agent_name, script_type)
                if not script_content:
                    broadcast_log(job_id, agent_name, error, "error")
                    if llm_attempt < llm_retries - 1:
                        broadcast_log(job_id, agent_name, "Retrying with validation error feedback...")
                        current_prompt = base_prompt + (
                            f"\n\nYOUR PREVIOUS RESPONSE FAILED VALIDATION WITH THIS ERROR:\n{error}\n"
                            "Please fix the error and provide the corrected script."
                        )
                        continue
                    else:
                        error_msgs.append(f"Failed to generate valid script for {sig}: {error}")
                        failed_any = True
                        break
                    
                script_hash = hashlib.sha256(script_content.encode("utf-8")).hexdigest()
                
                broadcast_log(job_id, agent_name,
                    f"[{sig}] Script generated successfully. SHA256: {script_hash[:16]}...")
                
                updates["script_contents"][sig] = script_content
                updates["script_hashes"][sig] = script_hash
                success = True
                break
                
            except Exception as e:
                error_message = f"Error during script generation for {sig}: {e}"
                broadcast_log(job_id, agent_name, error_message, "error")
                if llm_attempt == llm_retries - 1:
                    error_msgs.append(error_message)
                    failed_any = True
                    
        if not success:
            failed_any = True

    if failed_any:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": "; ".join(error_msgs), "script_generation_end_time": time.time()}
        
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return {**updates, "script_generation_end_time": time.time()}
