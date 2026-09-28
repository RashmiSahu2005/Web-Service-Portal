from app.graph.state import InstallationState, InstallationAttempt
from app.services.script_registry_service import ScriptRegistryService
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
import json
import re
from typing import Literal, List, Optional
from pydantic import BaseModel, Field

MAX_GENERATION_ATTEMPTS = 3

class FailureAnalysisResult(BaseModel):
    failure_category: Literal[
        "DOWNLOAD_FAILURE", "INVALID_PACKAGE", "NETWORK_FAILURE", "DNS_FAILURE",
        "REPOSITORY_FAILURE", "DEPENDENCY_FAILURE", "PERMISSION_FAILURE",
        "OS_INCOMPATIBILITY", "ARCHITECTURE_MISMATCH", "VERSION_MISMATCH",
        "PACKAGE_NOT_FOUND", "PACKAGE_HELD", "INSTALLATION_FAILURE",
        "VERIFICATION_FAILURE", "GUI_CONTEXT_FAILURE", "ROOT_EXECUTION_FAILURE",
        "TIMEOUT", "HOST_PACKAGE_MANAGER_INCOMPATIBLE", "EXECUTION_TIMEOUT", "UNKNOWN",
        "FLEETDM_INSTALLATION_EXECUTION_FAILURE", "FLEETDM_AUXILIARY_CHECK_FAILURE",
        "HOST_CONFIGURATION_FAILURE", "INVALID_UNVERIFIED_URL", "ARTIFACT_REQUIRED"
    ]
    root_cause: str
    suggested_fix: str
    retryable: bool
    research_valid: bool
    strategy_incompatible: bool = False
    failed_strategy: Optional[str] = None
    required_strategy_change: bool = False
    suggested_alternatives: List[str] = Field(default_factory=list)
    next_action: Literal["SCRIPT_GENERATION", "INSTALLATION_RESEARCH", "FAILED"]


def analyze_script_failure(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptFailureAnalyzer"
    stage_name = "SCRIPT_FAILURE_ANALYSIS"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Analyzing execution results to determine failure root cause")
    
    updates = {}

    # ── SUCCESS PATH ──────────────────────────────────────────────────────────
    if state.get("status") not in ["FAILED", "PARTIAL_SUCCESS"]:
        broadcast_log(job_id, agent_name, "Execution was successful, proceeding normally.")
        
        # Increment success_count for any reused (cached) scripts that succeeded
        script_reused_map = state.get("script_reused", {})
        script_registry_ids = state.get("script_registry_ids", {})
        for sig, reused in script_reused_map.items():
            if reused:
                registry_id = script_registry_ids.get(sig)
                if registry_id:
                    ScriptRegistryService.update_script_execution(registry_id, success=True)
            
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        updates["current_stage"] = "SCRIPT_FAILURE_ANALYSIS_COMPLETED"
        return updates

    # ── FAILURE PATH ─────────────────────────────────────────────────────────
    execution_results = state.get("execution_results", {})
    fleet_script_ids   = state.get("fleet_script_ids", {})
    script_reused_map  = state.get("script_reused", {})
    script_registry_ids = state.get("script_registry_ids", {})
    cached_failures    = state.get("cached_script_failures", {})
    
    failed_sigs = set()
    
    updates["script_failure_context"] = state.get("script_failure_context", {}).copy()
    updates["installation_attempts"] = state.get("installation_attempts", {}).copy()

    
    # ── 1. HANDLE CACHED-SCRIPT PRE-EXECUTION FAILURES ───────────────────────
    # These come from fleet_execution.py when a reused script's FleetDM ID no
    # longer exists or returns an error BEFORE an execution_id is ever created.
    for sig, cache_fail_info in cached_failures.items():
        broadcast_log(job_id, agent_name,
            f"[{sig}] Cached script pre-execution failure detected. "
            f"FleetDM script {cache_fail_info.get('fleet_script_id')} — "
            f"{cache_fail_info.get('error_message')}")
        
        # Invalidate the registry entry (sets status=INVALID and removes local mirror)
        registry_id = script_registry_ids.get(sig)
        if registry_id:
            broadcast_log(job_id, agent_name,
                f"[{sig}] Invalidating registry entry {registry_id} for stale cached script.")
            ScriptRegistryService.invalidate_script(registry_id)
        
        # Build a failure context entry so generation Attempt 1 knows why we're here
        if sig not in updates["script_failure_context"]:
            updates["script_failure_context"][sig] = []
        updates["script_failure_context"][sig].append({
            "attempt": 0,  # 0 = cache failure, not a generation attempt
            "script_type": state.get("current_script_type", {}).get(sig, "unknown"),
            "exit_code": "N/A",
            "error_output": cache_fail_info.get("error_message", ""),
            "analysis": (
                f"The previously cached FleetDM script could not be executed: "
                f"{cache_fail_info.get('reason', 'Unknown reason')}. "
                "Generate a fresh installation script."
            )
        })
        failed_sigs.add(sig)
        
    # ── 2. HANDLE RUNTIME EXECUTION FAILURES ─────────────────────────────────
    for exec_id, result in execution_results.items():
        exit_code = result.get("exit_code")
        output    = result.get("output", "")
        timeout   = result.get("host_timeout", False)
        script_id = result.get("script_id")
        
        message   = result.get("message", "")
        
        sig = next((k for k, v in fleet_script_ids.items() if str(v) == str(script_id)), None)
        
        # Check if fleet stopped it
        is_fleet_timeout = "Fleet stopped the script after 300 seconds" in output or "Fleet stopped the script after 300 seconds" in message
        if timeout or is_fleet_timeout:
            broadcast_log(job_id, agent_name,
                f"[{sig}] Execution {exec_id} timed out. Treating as EXECUTION_TIMEOUT.", "warning")
            
            if sig:
                failed_sigs.add(sig)
                
                # If this was a reused (cached) script...
                if script_reused_map.get(sig, False):
                    registry_id = script_registry_ids.get(sig)
                    if registry_id:
                        ScriptRegistryService.invalidate_script(registry_id)
                
                attempt_num = state.get("current_attempts", {}).get(sig, 1)
                apps_str = ", ".join(filter(None, [a.get("name") or a.get("application_name") for a in state.get("applications", [])]))
                
                if sig not in updates["script_failure_context"]:
                    updates["script_failure_context"][sig] = []
                    
                updates["script_failure_context"][sig].append({
                    "attempt": attempt_num,
                    "script_type": state.get("current_script_type", {}).get(sig),
                    "exit_code": "TIMEOUT",
                    "error_output": output[-2000:] if output else "FleetDM execution limit (300s) exceeded.",
                    "failure_category": "EXECUTION_TIMEOUT",
                    "failed_strategy": state.get("strategies", {}).get(sig, {}).get(apps_str, {}).get("recommended_method", "unknown"),
                    "strategy_incompatible": True,
                    "analysis": "FleetDM execution limit (300s) was exceeded. The current installation method is too slow or hung.",
                    "next_action": "INSTALLATION_RESEARCH"
                })
                
                if sig not in updates["installation_attempts"]:
                    updates["installation_attempts"][sig] = []
                
                updates["installation_attempts"][sig].append(InstallationAttempt(
                    attempt_number=attempt_num,
                    strategy=state.get("strategies", {}).get(sig, {}).get(apps_str, {}).get("recommended_method", "unknown"),
                    script_id=str(script_id),
                    script=state.get("script_contents", {}).get(sig, ""),
                    exit_code=-1 if exit_code is None else exit_code,
                    output=output,
                    error="TIMEOUT",
                    root_cause="Execution exceeded 300 seconds FleetDM limit.",
                    corrective_action="Use alternative, faster installation method.",
                    verification_result={}
                ).model_dump())
                
            continue
            
        if exit_code is not None and exit_code != 0:
            broadcast_log(job_id, agent_name,
                f"[DeployIQ][ScriptGeneration] Application={state.get('application_name')} "
                f"Attempt={state.get('current_attempts', {}).get(sig, 1)}/3 "
                f"Status=FAILED ExitCode={exit_code}", "warning")
            
            if sig:
                failed_sigs.add(sig)
                
                # If this was a reused (cached) script that failed at runtime — invalidate it
                if script_reused_map.get(sig, False):
                    registry_id = script_registry_ids.get(sig)
                    if registry_id:
                        broadcast_log(job_id, agent_name,
                            f"[{sig}] Runtime failure of cached script. Invalidating registry entry {registry_id}.")
                        ScriptRegistryService.invalidate_script(registry_id)
                
                # Build failure context for the LLM
                applications = state.get("applications", [])
                app_names = [a.get("name") or a.get("application_name") for a in applications]
                apps_str = ", ".join(filter(None, app_names))
                
                trimmed_output = output[-2000:] if output else "No output provided"
                
                analysis_prompt = f"""Analyze this failed installation script execution.

Target Applications: {apps_str}
OS Signature: {sig}
Exit Code: {exit_code}
Script Type: {state.get("current_script_type", {}).get(sig)}
Previous Attempts Context: {len(updates["script_failure_context"].get(sig, []))} previous failures.

Output/Error (last 2000 chars):
{trimmed_output}

Provide ONLY a JSON object conforming exactly to this schema:
{{
  "failure_category": "REPOSITORY_FAILURE | DEPENDENCY_FAILURE | NETWORK_FAILURE | INSTALLATION_FAILURE | VERIFICATION_FAILURE | DOWNLOAD_FAILURE | DNS_FAILURE | EXECUTION_TIMEOUT | PACKAGE_NOT_FOUND | HOST_PACKAGE_MANAGER_INCOMPATIBLE | FLEETDM_INSTALLATION_EXECUTION_FAILURE | HOST_CONFIGURATION_FAILURE | INVALID_UNVERIFIED_URL | ARTIFACT_REQUIRED | UNKNOWN",
  "root_cause": "Detailed explanation of what failed",
  "suggested_fix": "Concrete, actionable fix — must differ materially from what already failed",
  "retryable": true or false,
  "research_valid": true if the existing installation method/strategy is still correct but the script had a fixable issue — false only if the entire approach needs to be reconsidered,
  "strategy_incompatible": true if the chosen package manager or method failed due to host restrictions (e.g. snap cannot run due to temporary filesystem issues), otherwise false,
  "failed_strategy": "The package manager or method that failed (e.g., 'snap', 'apt', 'tarball')",
  "required_strategy_change": true if you must switch to a different method (e.g. from snap to .deb), otherwise false,
  "suggested_alternatives": ["official_deb", "official_tarball", etc] - a list of methods to try next,
  "next_action": "SCRIPT_GENERATION" if research_valid is true and the fix can be applied in a new script — "INSTALLATION_RESEARCH" if the approach must change — "FAILED" if not retryable
}}

CRITICAL RULE 1: If the installation strategy was 'snap' and the output indicates host restrictions (e.g. 'cannot create temporary directory', 'snapd is not running', 'too early for operation', 'daemon unavailable', 'policy restrictions', 'noexec restrictions', 'cgroups error'), you MUST output 'HOST_PACKAGE_MANAGER_INCOMPATIBLE', set 'strategy_incompatible' to true, 'required_strategy_change' to true, and 'next_action' to 'INSTALLATION_RESEARCH'.
CRITICAL RULE 2: If the error is 'PACKAGE_NOT_FOUND', or an unrecoverable 'APT_REPOSITORY_FAILURE' (not just a GPG key issue), you MUST set 'research_valid' to false, 'required_strategy_change' to true, and 'next_action' to 'INSTALLATION_RESEARCH'.
CRITICAL RULE 3: If `curl` or `wget` returns a DNS resolution error (e.g., 'Could not resolve host') or HTTP 404 Not Found on a downloaded artifact or GPG key URL, classify it as 'INVALID_UNVERIFIED_URL'. Set 'research_valid' to false and 'next_action' to 'INSTALLATION_RESEARCH'. However, if the failed strategy was a package manager (e.g., 'apt', 'yum', 'rpm', 'repository'), DO NOT set 'required_strategy_change' to true; instead, advise the research layer to find the correct, documented repository URLs while preserving the repository strategy. If the strategy was a direct artifact, set 'required_strategy_change' to true.
CRITICAL RULE 4: If the script outputs 'DEPLOYIQ_FAILURE_CATEGORY=ARTIFACT_REQUIRED', set 'failure_category' to 'ARTIFACT_REQUIRED', set 'retryable' to false, and 'next_action' to 'FAILED'.
"""
                try:
                    raw_analysis = LLMService.generate(analysis_prompt, json_mode=True)
                    clean = raw_analysis.strip()
                    if clean.startswith("```json"): clean = clean[7:]
                    elif clean.startswith("```"): clean = clean[3:]
                    if clean.endswith("```"): clean = clean[:-3]
                    clean = clean.strip()
                    parsed = json.loads(clean)
                    analysis = FailureAnalysisResult.model_validate(parsed)
                    broadcast_log(job_id, agent_name,
                        f"[{sig}] Root cause identified ({analysis.failure_category}): {analysis.root_cause[:150]}...")
                except Exception as e:
                    broadcast_log(job_id, agent_name, f"LLM analysis failed: {e}. Using fallback.", "warning")
                    analysis = FailureAnalysisResult(
                        failure_category="UNKNOWN",
                        root_cause=f"Analysis failed: {e}",
                        suggested_fix="Retry with new research strategy",
                        retryable=True,
                        research_valid=False,
                        strategy_incompatible=True,
                        failed_strategy="unknown",
                        required_strategy_change=True,
                        suggested_alternatives=["tarball", "deb"],
                        next_action="INSTALLATION_RESEARCH"
                    )
                
                if sig not in updates["script_failure_context"]:
                    updates["script_failure_context"][sig] = []
                    
                attempt_num = state.get("current_attempts", {}).get(sig, 1)
                updates["script_failure_context"][sig].append({
                    "attempt": attempt_num,
                    "script_type": state.get("current_script_type", {}).get(sig),
                    "exit_code": exit_code,
                    "error_output": trimmed_output,
                    "failure_category": analysis.failure_category,
                    "failed_strategy": analysis.failed_strategy,
                    "strategy_incompatible": analysis.strategy_incompatible,
                    "required_strategy_change": analysis.required_strategy_change,
                    "analysis": analysis.root_cause,
                    "next_action": analysis.next_action
                })
                
                if sig not in updates["installation_attempts"]:
                    updates["installation_attempts"][sig] = []
                
                updates["installation_attempts"][sig].append(InstallationAttempt(
                    attempt_number=attempt_num,
                    strategy=state.get("strategies", {}).get(sig, {}).get(apps_str, {}).get("recommended_method", "unknown"),
                    script_id=str(script_id),
                    script=state.get("script_contents", {}).get(sig, ""),
                    exit_code=exit_code,
                    output=output,
                    error=trimmed_output,
                    root_cause=analysis.root_cause,
                    corrective_action=analysis.suggested_fix,
                    verification_result={}
                ).model_dump())
                
                broadcast_log(job_id, agent_name,
                    f"[{sig}] Passing failure context to next action: {analysis.next_action}")

    # ── 3. DECIDE: RETRY OR FINAL FAIL ───────────────────────────────────────
    if not failed_sigs:
        # status was FAILED but we found no explainable failure — shouldn't happen
        broadcast_log(job_id, agent_name,
            "No script failures detected, but status was FAILED. "
            "This may be a transient error. Marking FAILED.", "warning")
        updates["status"] = "FAILED"
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates

    updates["current_attempts"] = state.get("current_attempts", {}).copy()
    maximum_attempts = state.get("maximum_attempts", {}).copy()
    
    can_retry = False
    for sig in failed_sigs:
        current_attempt = updates["current_attempts"].get(sig, 0)
        
        # For cached-script failures (attempt 0), generation starts at attempt 1.
        # For runtime failures, attempt number is already tracked.
        if current_attempt == 0:
            # First generation attempt after a cache failure
            updates["current_attempts"][sig] = 1
            maximum_attempts[sig] = MAX_GENERATION_ATTEMPTS
            can_retry = True
            broadcast_log(job_id, agent_name,
                f"[DeployIQ][ScriptGeneration] Application={state.get('application_name')} "
                f"Attempt=1/{MAX_GENERATION_ATTEMPTS} Reason=CACHED_SCRIPT_INVALID", "warning")
        elif current_attempt < maximum_attempts.get(sig, MAX_GENERATION_ATTEMPTS):
            next_attempt = current_attempt + 1
            updates["current_attempts"][sig] = next_attempt
            maximum_attempts[sig] = max(maximum_attempts.get(sig, MAX_GENERATION_ATTEMPTS), MAX_GENERATION_ATTEMPTS)
            can_retry = True
            broadcast_log(job_id, agent_name,
                f"[DeployIQ][ScriptGeneration] Application={state.get('application_name')} "
                f"Attempt={next_attempt}/{MAX_GENERATION_ATTEMPTS} UsingPreviousFailureContext=True", "warning")
        else:
            broadcast_log(job_id, agent_name,
                f"[{sig}] Max attempts ({MAX_GENERATION_ATTEMPTS}) reached. No more retries.", "error")
            # Increment failure count for cached scripts
            if script_reused_map.get(sig, False):
                registry_id = script_registry_ids.get(sig)
                if registry_id:
                    ScriptRegistryService.update_script_execution(registry_id, success=False)

    updates["maximum_attempts"] = maximum_attempts

    if can_retry:
        # Reset reuse flags so script_generation runs the LLM
        updates["script_reused"] = {sig: False for sig in failed_sigs}
        updates["fleet_script_ids"] = {}
        updates["cached_script_failures"] = {}  # Consumed — clear for next pass
        
        # Determine routing from failure analysis:
        # - If any failure says next_action="FAILED", we stop immediately and mark as FAILED (or ARTIFACT_REQUIRED).
        # - If all failures say research_valid=True → SCRIPT_GENERATION (re-generate with failure context)
        # - Otherwise → INSTALLATION_RESEARCH
        
        all_research_valid = True
        has_fatal_failure = False
        fatal_category = "FAILED"
        
        for sig in failed_sigs:
            failure_contexts = updates["script_failure_context"].get(sig, [])
            if failure_contexts:
                last_context = failure_contexts[-1]
                last_action = last_context.get("next_action", "INSTALLATION_RESEARCH")
                
                if last_action == "FAILED":
                    has_fatal_failure = True
                    # Check if it was ARTIFACT_REQUIRED
                    if last_context.get("failure_category") == "ARTIFACT_REQUIRED":
                        fatal_category = "ARTIFACT_REQUIRED"
                        
                if last_action != "SCRIPT_GENERATION":
                    all_research_valid = False
            else:
                all_research_valid = False
                
        if has_fatal_failure:
            broadcast_log(job_id, agent_name, f"Fatal error identified. Halting retries. Status={fatal_category}", "error")
            updates["status"] = fatal_category
        elif all_research_valid:
            # Research is still valid — regenerate script with failure context
            updates["status"] = "RETRYING_SCRIPT"
            broadcast_log(job_id, agent_name,
                "Research still valid — retrying script generation with failure context.")
        else:
            # Need fresh research — do NOT reset attempt counters to prevent infinite loops
            # The research_attempts counter will persist and increment naturally
            tavily_attempted = dict(state.get("tavily_attempted") or {})
            for sig in failed_sigs:
                tavily_attempted[sig] = False  # Allow Tavily to run again
            updates["tavily_attempted"] = tavily_attempted
            updates["status"] = "RETRYING"
            broadcast_log(job_id, agent_name,
                "Research invalidated — routing back to INSTALLATION_RESEARCH for an alternative strategy.")
        
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    else:
        broadcast_log(job_id, agent_name,
            f"Max attempts ({MAX_GENERATION_ATTEMPTS}) exhausted for all failed OS groups. "
            "Marking application FAILED.", "error")
        updates["status"] = "FAILED"
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        
    return updates
