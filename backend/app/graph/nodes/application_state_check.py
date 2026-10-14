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


from app.providers import ApplicationProviderRegistry


def _generate_state_check_script(app_strategies: dict, is_windows: bool = False, os_name: str = "linux") -> str:
    if not is_windows:
        script_lines = ['#!/bin/bash', 'set -o pipefail', 'printf "{"']
        items = list(app_strategies.items())
        for i, (app_name, strategy) in enumerate(items):
            cmd = strategy.get("installed_version_command", [])
            latest_cmd = strategy.get("latest_version_command", [])
            comma = "," if i < len(items) - 1 else ""

            # Build command string safely — use explicit join
            cmd_str = " ".join(str(c) for c in cmd) if cmd else ""
            latest_cmd_str = " ".join(str(c) for c in latest_cmd) if latest_cmd else ""

            provider = ApplicationProviderRegistry.get_provider(app_name, os_name)
            script_lines.append(provider.generate_state_check_bash(os_name, cmd_str, latest_cmd_str, requested_app_name=app_name))
            if comma:
                script_lines.append(f'printf "{comma}"')

        script_lines.append('printf "}\\n"')
        return "\n".join(script_lines)

    # Windows — Python-based detection
    checks = {}
    for app_name, strategy in app_strategies.items():
        checks[app_name] = {
            "installed_cmd": strategy.get("installed_version_command", []),
            "latest_cmd": strategy.get("latest_version_command", [])
        }

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

    for app_name, cmds in checks.items():
        result[app_name] = {{"installed_raw": None, "latest_raw": None, "detection_method": None, "exit_code": -1, "error_message": None}}
        installed_cmd = cmds.get("installed_cmd")
        latest_cmd = cmds.get("latest_cmd")

        if latest_cmd:
            try:
                res_l = subprocess.run(latest_cmd, capture_output=True, text=True, timeout=10)
                if res_l.returncode == 0:
                    result[app_name]["latest_raw"] = extract_version(res_l.stdout.strip())
            except Exception:
                pass

        if installed_cmd:
            try:
                res = subprocess.run(installed_cmd, capture_output=True, text=True, timeout=10)
                result[app_name]["exit_code"] = res.returncode
                if res.returncode == 0:
                    ver = extract_version(res.stdout.strip())
                    if ver:
                        result[app_name]["installed_raw"] = ver
                        result[app_name]["detection_method"] = "windows_subprocess"
                    else:
                        result[app_name]["exit_code"] = 1
                        result[app_name]["error_message"] = f"VERSION_DETECTION_FAILED: Command succeeded but no version found in: {{res.stdout.strip()[:200]}}"
                else:
                    result[app_name]["error_message"] = f"VERSION_DETECTION_FAILED: {{res.stderr.strip()[:200]}}"
            except Exception as e:
                result[app_name]["error_message"] = f"VERSION_DETECTION_FAILED: {{str(e)[:200]}}"

    print(json.dumps(result))

if __name__ == "__main__":
    check()
"""


def _upload_state_check_script(content: str, job_id: str, agent_name: str, ext: str = ".sh", is_windows: bool = False) -> str:
    if ext == ".sh" and not is_windows:
        # Transport wrapper: avoids noexec mount issues on /tmp
        content = f"bash -s <<'DEPLOYIQ_SCRIPT'\n{content}\nDEPLOYIQ_SCRIPT\n"

    fd, temp_path = tempfile.mkstemp(prefix="apphub_state_check_", suffix=ext)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)

        os.chmod(temp_path, 0o755)

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
    """
    Run the state-check script on a host via FleetDM and return the parsed JSON result.
    Returns empty dict {} only on communication/timeout failures (not on detection failures).
    """
    try:
        run_response = FleetDMService.run_script(host_id, script_id)
        if not run_response:
            broadcast_log(job_id, agent_name, f"FleetDM failed to start state-check script on host {host_id}", "error")
            return {}

        exec_id = run_response.get("execution_id")
        if not exec_id:
            broadcast_log(job_id, agent_name, f"No execution_id returned for state-check on host {host_id}", "error")
            return {}

        max_attempts = 18  # 18 × polling_interval
        attempts = 0

        while attempts < max_attempts:
            await asyncio.sleep(settings.POLLING_INTERVAL)
            result = FleetDMService.get_script_result(exec_id)
            if not result:
                attempts += 1
                continue

            exit_code = result.get("exit_code")
            host_timeout = result.get("host_timeout", False)

            if exit_code is not None or host_timeout:
                if host_timeout:
                    broadcast_log(job_id, agent_name, f"State-check script timed out on host {host_id}", "warning")
                    return {}

                if exit_code == 0:
                    raw_output = result.get("output", "").strip()
                    broadcast_log(job_id, agent_name, f"[Host {host_id}] State-check raw output (first 500 chars): {raw_output[:500]}")
                    try:
                        parsed_json = json.loads(raw_output)
                        return parsed_json
                    except Exception as parse_err:
                        broadcast_log(job_id, agent_name,
                            f"[Host {host_id}] Failed to parse state-check JSON output: {parse_err}. "
                            f"Raw output: {raw_output[:300]}", "error")
                        # Return a sentinel that signals parse failure
                        return {"__parse_error__": True, "raw": raw_output[:200]}
                else:
                    broadcast_log(job_id, agent_name,
                        f"[Host {host_id}] State-check script returned exit_code={exit_code}. "
                        f"Output: {result.get('output', '')[:300]}", "warning")
                    return {}

            attempts += 1

        broadcast_log(job_id, agent_name, f"State-check polling timed out for host {host_id} (max_attempts={max_attempts})", "warning")
        return {}

    except Exception as e:
        broadcast_log(job_id, agent_name, f"Error running state-check on host {host_id}: {e}", "error")
        return {}


async def check_application_state(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationStateCheckAgent"
    stage_name = "APPLICATION_STATE_CHECK"

    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting application state check")

    updates = {
        "application_states": {},
        "installed_versions": {},
        "latest_versions_from_host": {},
        "hosts_requiring_installation": [],
        "applications": state.get("applications", [])
    }

    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK"]:
        broadcast_log(job_id, agent_name, f"Skipping state check — workflow status is already {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates

    applications = state.get("applications", [])
    os_groups = state.get("os_groups", {})
    strategies = state.get("strategies", {})

    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN — Mocking state check for all hosts")
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
            broadcast_log(job_id, agent_name, f"No strategy found for OS group {sig} — skipping.", "warning")
            for host_id in host_ids:
                if host_id not in updates["application_states"]:
                    updates["application_states"][host_id] = {}
                for app in applications:
                    app_name = app.get("name") or app.get("application_name")
                    if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                        updates["application_states"][host_id][app_name] = "STATE_CHECK_UNAVAILABLE"
            continue

        is_windows = "windows" in sig.lower()
        ext = ".py" if is_windows else ".sh"
        script_content = _generate_state_check_script(app_strategies, is_windows=is_windows, os_name=sig)
        script_id = _upload_state_check_script(script_content, job_id, agent_name, ext=ext, is_windows=is_windows)

        if not script_id:
            broadcast_log(job_id, agent_name, f"Failed to upload state-check script for OS group {sig}.", "warning")
            for host_id in host_ids:
                if host_id not in updates["application_states"]:
                    updates["application_states"][host_id] = {}
                for app in applications:
                    app_name = app.get("name") or app.get("application_name")
                    if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED"]:
                        updates["application_states"][host_id][app_name] = "STATE_CHECK_UNAVAILABLE"
            continue

        for host_id in host_ids:
            broadcast_log(job_id, agent_name, f"Running state-check on host {host_id} (OS: {sig})...")
            res = await _check_on_host(host_id, script_id, job_id, agent_name)

            if host_id not in updates["installed_versions"]:
                updates["installed_versions"][host_id] = {}
            if host_id not in updates["latest_versions_from_host"]:
                updates["latest_versions_from_host"][host_id] = {}
            if host_id not in updates["application_states"]:
                updates["application_states"][host_id] = {}

            # Check for communication failure (empty dict means comms failed, not detection failed)
            comms_failed = len(res) == 0
            parse_error = res.get("__parse_error__", False)

            active_app_name = state.get("application_name")
            for app in applications:
                app_name = app.get("name") or app.get("application_name")
                if app_name != active_app_name:
                    continue

                is_update = (app.get("operation") == "UPDATE")

                # Handle communication / parse failures
                if comms_failed or parse_error:
                    broadcast_log(job_id, agent_name,
                        f"[{app_name}] State-check communication failure on host {host_id} "
                        f"(comms_failed={comms_failed}, parse_error={parse_error})", "error")
                    if is_update:
                        _block_update(app, app_name, host_id, "STATE_CHECK_FAILED",
                                      "Failed to communicate with host or parse state-check output",
                                      state, job_id, agent_name, updates)
                    else:
                        updates["application_states"][host_id][app_name] = "STATE_CHECK_UNAVAILABLE"
                        if host_id not in updates["hosts_requiring_installation"]:
                            updates["hosts_requiring_installation"].append(host_id)
                    continue

                from app.utils.version_utils import app_matches
                app_res = res.get(app_name)
                if not app_res:
                    for k, v in res.items():
                        if app_matches(k, app_name):
                            app_res = v
                            break
                if not app_res and len(res) == 1 and not res.get("__parse_error__"):
                    app_res = list(res.values())[0]
                if not app_res:
                    app_res = {}

                installed = app_res.get("installed_raw")
                latest_from_host = app_res.get("latest_raw")
                package_ver = app_res.get("package_version")
                binary_ver = app_res.get("binary_version")
                app_present = app_res.get("app_present", False)
                exit_code_in_json = app_res.get("exit_code", -1)
                detection_method = app_res.get("method") or app_res.get("detection_method")
                detection_error = app_res.get("error_message")

                # Normalize "null" string → None
                if isinstance(latest_from_host, str) and latest_from_host.lower() in ("null", "none", ""):
                    latest_from_host = None
                if isinstance(installed, str) and installed.lower() in ("null", "none", ""):
                    installed = None
                if isinstance(package_ver, str) and package_ver.lower() in ("null", "none", ""):
                    package_ver = None
                if isinstance(binary_ver, str) and binary_ver.lower() in ("null", "none", ""):
                    binary_ver = None

                # Structured state-check logging
                broadcast_log(job_id, agent_name,
                    f"[Application: {app_name}] [Operation: {app.get('operation', 'INSTALL')}] [Host: {host_id}]\n"
                    f"  installed_detected: {bool(installed or package_ver or binary_ver)}\n"
                    f"  installed_version: {installed or package_ver or binary_ver or 'None'}\n"
                    f"  package_version: {package_ver or 'None'}\n"
                    f"  binary_version: {binary_ver or 'None'}\n"
                    f"  detection_method: {detection_method or 'None'}\n"
                    f"  detection_exit_code: {exit_code_in_json}\n"
                    f"  latest_from_pkg_mgr: {latest_from_host or 'None'}\n"
                    f"  error: {detection_error or 'None'}"
                )

                # Canonical version calculation (prefer package manager)
                from app.utils.version_utils import canonicalize_version
                pkg_mgr = app_strategies.get(app_name, {}).get("package_manager") or "APT"
                canonical_ver, ver_source = canonicalize_version(
                    binary_version=binary_ver or installed,
                    package_version=package_ver or installed,
                    package_manager=pkg_mgr
                )

                app["installed_binary_version"] = binary_ver or installed
                app["installed_package_version"] = package_ver or latest_from_host
                app["canonical_installed_version"] = canonical_ver
                app["version_source"] = ver_source
                app["installed_version"] = canonical_ver or installed or package_ver or binary_ver
                app["detection_method"] = detection_method

                updates["installed_versions"][host_id][app_name] = canonical_ver or installed or package_ver or binary_ver
                if latest_from_host:
                    updates["latest_versions_from_host"][host_id][app_name] = latest_from_host

                broadcast_log(job_id, agent_name,
                    f"[{app_name}] Canonical installed version: {canonical_ver or 'UNKNOWN'} (source: {ver_source})")
                if detection_error:
                    broadcast_log(job_id, agent_name,
                        f"[{app_name}] Detection error message: {detection_error}", "warning")

                # ── Determine app_state ───────────────────────────────────────────
                if canonical_ver or installed or package_ver or binary_ver:
                    app_state = "INSTALLED_VERSION_DETECTED"
                elif exit_code_in_json == 0 and not app_present:
                    app_state = "APPLICATION_NOT_INSTALLED"
                elif exit_code_in_json == 1 or app_present:
                    app_state = "VERSION_DETECTION_FAILED"
                else:
                    app_state = "VERSION_DETECTION_FAILED"

                # ── UPDATE-specific guardrails ────────────────────────────────────
                if is_update:
                    if app_state == "APPLICATION_NOT_INSTALLED":
                        app["update_fallback_to_install"] = True
                        app["operation"] = "INSTALL"
                        broadcast_log(job_id, agent_name, f"[{app_name}] was requested to UPDATE but is not installed on host {host_id}. Falling back to fresh INSTALL.", "info")
                        # We intentionally do not 'continue' here so it falls through to the INSTALL path below.
                    elif app_state in ("VERSION_DETECTION_FAILED", "STATE_CHECK_FAILED"):
                        _block_update(app, app_name, host_id, "VERSION_DETECTION_FAILED",
                                      detection_error or f"Unable to determine installed version of {app_name}. "
                                      f"All detection methods failed. Check PATH/binary on host {host_id}.",
                                      state, job_id, agent_name, updates)
                        continue

                    if app_state == "INSTALLED_VERSION_DETECTED" and not canonical_ver:
                        # installed_raw exists but canonicalization failed — block
                        _block_update(app, app_name, host_id, "VERSION_DETECTION_FAILED",
                                      f"Version string '{installed}' could not be normalized for safe comparison.",
                                      state, job_id, agent_name, updates)
                        continue

                # ── INSTALL path ──────────────────────────────────────────────────
                if app.get("status") not in ["SUCCESS", "ALREADY_INSTALLED", "FAILED"]:
                    updates["application_states"][host_id][app_name] = app_state

                if app_state in ["APPLICATION_NOT_INSTALLED", "VERSION_DETECTION_FAILED",
                                 "STATE_CHECK_FAILED", "CURRENT_VERSION_UNKNOWN"]:
                    if host_id not in updates["hosts_requiring_installation"]:
                        updates["hosts_requiring_installation"].append(host_id)

        # Cleanup temporary state-check script from FleetDM
        if script_id:
            try:
                FleetDMService.delete_script(int(script_id))
                broadcast_log(job_id, agent_name, f"Cleaned up state-check script {script_id} from FleetDM")
            except Exception as e:
                broadcast_log(job_id, agent_name, f"Failed to clean up state-check script {script_id}: {e}", "warning")

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates


def _block_update(app: dict, app_name: str, host_id: int, failure_category: str,
                  reason: str, state: dict, job_id: str, agent_name: str, updates: dict,
                  send_email: bool = False):
    """
    Mark an UPDATE as blocked with a clear failure category and reason.
    Never silently converts to NO_UPDATE_REQUIRED.
    """
    app["status"] = "FAILED"
    app["failure_category"] = failure_category
    app["error_message"] = reason
    updates["status"] = "FAILED"

    broadcast_log(job_id, agent_name,
        f"[{app_name}] UPDATE BLOCKED [{failure_category}] on host {host_id}: {reason}", "error")

    if send_email and failure_category == "APPLICATION_NOT_INSTALLED":
        try:
            from app.services.email_service import EmailService
            requester_email = state.get("requester_email")
            if requester_email:
                email_msg = state.get("email_message", {})
                msg_id = email_msg.get("message_id") if isinstance(email_msg, dict) else None
                EmailService.send_update_blocked_email(
                    recipient_email=requester_email,
                    application_name=app_name,
                    hostname=host_id,
                    in_reply_to=msg_id
                )
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Failed to send update-blocked email: {e}", "warning")

    elif failure_category == "VERSION_DETECTION_FAILED":
        try:
            from app.services.email_service import EmailService
            requester_email = state.get("requester_email")
            if requester_email:
                email_msg = state.get("email_message", {})
                msg_id = email_msg.get("message_id") if isinstance(email_msg, dict) else None
                EmailService.send_version_detection_failed_email(
                    recipient_email=requester_email,
                    application_name=app_name,
                    hostname=host_id,
                    reason=reason,
                    in_reply_to=msg_id
                )
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Failed to send version-detection-failed email: {e}", "warning")
