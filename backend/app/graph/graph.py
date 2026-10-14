# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END
from app.graph.state import InstallationState
from app.graph.nodes.validation import validate_request
import time
from app.graph.nodes.host_discovery import discover_hosts
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.script_registry_lookup import script_registry_lookup
from app.graph.nodes.installation_research import installation_research
from app.graph.nodes.installation_research_validation import validate_installation_research
from app.graph.nodes.script_generation import generate_script
from app.graph.nodes.script_validation import validate_script
from app.graph.nodes.risk_analysis import analyze_risk
from app.graph.nodes.fleet_execution import execute_fleet
from app.graph.nodes.monitoring import monitor_execution
from app.graph.nodes.script_failure_analysis import analyze_script_failure
from app.graph.nodes.notification import send_notification
from app.graph.nodes.os_detection import detect_os
from app.graph.nodes.application_strategy_lookup import application_strategy_lookup
from app.graph.nodes.application_strategy_discovery import application_strategy_discovery

from app.database.database import SessionLocal
from app.database.repositories.job_repository import job_repo
from app.graph.nodes.utils import broadcast_log

def _is_cancelled(state: InstallationState):
    if state.get("is_cancelled") or state.get("status") == "CANCELLED":
        return True
        
    job_id = state.get("job_id")
    if job_id:
        db = SessionLocal()
        try:
            job = job_repo.get(db, job_id)
            if job and job.status == "CANCELLED":
                return True
        finally:
            db.close()
    return False

def route_after_validation(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "notification"
    return "host_discovery"

def route_after_host_discovery(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "notification"
    return "os_detection"

def route_after_os_detection(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "notification"
    return "prepare_current_application"

def prepare_current_application(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationIterator"
    
    applications = state.get("applications", [])
    current_index = state.get("current_app_index", 0)
    
    if current_index >= len(applications):
        return {"current_stage": "ITERATION_COMPLETE"}
        
    app = applications[current_index]
    app_name = app.get("name") or app.get("application_name")
    requested_version = app.get("version") or app.get("requested_version") or "Latest"
    operation = app.get("operation") or "INSTALL"
    
    broadcast_log(job_id, agent_name, f"========================================")
    broadcast_log(job_id, agent_name, f"--- Processing Application {current_index + 1}/{len(applications)}: {app_name} (Operation: {operation}) ---")
    broadcast_log(job_id, agent_name, f"========================================")
    
    # Return updates resetting state variables to clean values for the current iteration
    return {
        "application_name": app_name,
        "version": requested_version,
        "operation": operation,
        "current_app_index": current_index,
        "target_version": None,
        "strategies": {},
        "strategy_reused": {},
        # Installation research state (reset per app)
        "research_results": {},
        "research_skipped": {},
        "installed_versions": {},
        "application_states": {},
        "hosts_requiring_installation": [],
        "script_contents": {},
        "script_hashes": {},
        "script_reused": {},
        "script_registry_ids": {},
        "risk_scores": {},
        "risk_levels": {},
        "risk_reasons_map": {},
        "fleet_script_ids": {},
        "execution_ids": [],
        "execution_results": {},
        "installation_script_deleted": {},
        "installation_cleanup_error": {},
        "installation_timeout": {},
        "current_attempts": {},
        "maximum_attempts": {},
        "current_script_type": {},
        "script_failure_context": {},
        "cached_script_failures": {},
        "installation_attempts": {},
        # Research retry state — MUST be reset per application
        "research_attempts": {},
        "max_research_attempts": {},
        "tavily_attempted": {},
        "verification_script_contents": {},
        "verification_fleet_script_ids": {},
        "verification_execution_ids": [],
        "verification_execution_results": {},
        "verification_script_deleted": {},
        "verification_cleanup_error": {},
        "verification_timeout": {},
        "application_start_time": time.time(),
        "research_start_time": None,
        "research_end_time": None,
        "script_generation_start_time": None,
        "script_generation_end_time": None,
        "fleet_execution_start_time": None,
        "fleet_execution_end_time": None,
        "application_end_time": None
    }

def route_after_prepare_current_application(state: InstallationState):
    applications = state.get("applications", [])
    current_index = state.get("current_app_index", 0)
    if current_index >= len(applications) or state.get("current_stage") == "ITERATION_COMPLETE":
        return "notification"
    return "application_strategy_lookup"

def route_after_strategy_lookup(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"
    
    os_groups = state.get("os_groups", {})
    strategy_reused = state.get("strategy_reused", {})
    
    if os_groups and all(strategy_reused.get(sig, False) for sig in os_groups):
        return "application_state_check"
    return "application_strategy_discovery"

def route_after_strategy_discovery(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"
    return "application_state_check"

from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.version_decision import version_decision

def route_after_application_state_check(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") in ["FAILED", "UPDATE_BLOCKED"]: return "store_application_result"
    return "latest_version_discovery"

def route_after_latest_version_discovery(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"
    return "version_decision"

def route_after_version_decision(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"
    
    hosts_requiring_installation = state.get("hosts_requiring_installation", [])
    if not hosts_requiring_installation:
        # All hosts are already up-to-date, no installation required
        return "store_application_result"
        
    return "script_registry_lookup"

def route_after_script_registry_lookup(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"

    os_groups = state.get("os_groups", {})
    script_reused = state.get("script_reused", {})

    # Fast path: every OS group has a reused script — skip research entirely
    if os_groups and all(script_reused.get(sig, False) for sig in os_groups):
        return "script_generation"  # script_generation will skip (script_reused=True)

    # At least one OS group needs a new script — run Installation Research first
    return "installation_research"

def route_after_installation_research(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED": return "store_application_result"
    return "installation_research_validation"

def route_after_installation_research_validation(state: InstallationState):
    if _is_cancelled(state): return "notification"
    status = state.get("status")
    
    if status in ["RESEARCH_ERROR", "RESEARCH_INSUFFICIENT"]:
        research_attempts = state.get("research_attempts", {})
        max_research_attempts = state.get("max_research_attempts", {})
        
        failed_hard = False
        
        for sig, attempt in research_attempts.items():
            max_for_sig = max_research_attempts.get(sig, 3)
            # attempt has already been incremented in installation_research
            if attempt >= max_for_sig:
                failed_hard = True
                
        if failed_hard:
            return "store_application_result"
            
        return "installation_research"
        
    if status in ["FAILED", "ARTIFACT_REQUIRED", "UPDATE_REQUIRES_HUMAN_APPROVAL"]:
        return "store_application_result"
    return "script_generation"

def route_after_script_generation(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") in ["FAILED", "PARTIAL_SUCCESS"]: return "script_failure_analysis"
    return "script_validation"

def route_after_script_validation(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") in ["FAILED", "PARTIAL_SUCCESS"]: return "script_failure_analysis"
    return "risk_analysis"


def route_after_risk_analysis(state: InstallationState):
    if _is_cancelled(state): return "notification"
    if state.get("status") == "FAILED":
        return "store_application_result"
    if state.get("status") == "BLOCKED_HIGH_RISK":
        return "script_failure_analysis"
    return "fleet_execution"

def route_after_fleet_execution(state: InstallationState):
    return "monitoring"

def route_after_installation_script_cleanup(state: InstallationState):
    if state.get("status") in ["FAILED", "PARTIAL_SUCCESS"]:
        return "script_failure_analysis"
    return "store_application_result"

def route_after_script_failure_analysis(state: InstallationState):
    if _is_cancelled(state): return "notification"
    status = state.get("status")
    if status == "RETRYING_SCRIPT":
        return "script_generation"
    if status == "RETRYING":
        return "installation_research"
    return "store_application_result"

def store_application_result(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationIterator"
    
    applications = list(state.get("applications", []))
    current_index = state.get("current_app_index", 0)
    
    if current_index >= len(applications):
        return {"current_stage": "ALL_APPLICATIONS_PROCESSED"}
        
    app = dict(applications[current_index])
    app_name = state.get("application_name")
    
    # Determine the status of the current application
    app_states = state.get("application_states", {})
    first_host_id = state.get("host_ids")[0] if state.get("host_ids") else None
    host_state = app_states.get(first_host_id, {}).get(app_name) if first_host_id is not None else None
    
    app_status = "FAILED"
    inst_status = app.get("installation_status", "UNKNOWN")

    if state.get("status") == "TIMEOUT" or app.get("status") == "TIMEOUT":
        app_status = "TIMEOUT"
    elif app.get("status") in ["FAILED", "UPDATE_BLOCKED", "AWAITING_USER_CLARIFICATION"]:
        # Preserve specific failure_category for clear UI communication
        app_status = app.get("status")
    elif app.get("failure_category") in ["VERSION_DETECTION_FAILED", "APPLICATION_NOT_INSTALLED",
                                          "STATE_CHECK_FAILED", "CURRENT_VERSION_UNKNOWN",
                                          "LATEST_VERSION_UNVERIFIED", "VERSION_COMPARISON_FAILED",
                                          "TARGET_VERSION_UNKNOWN"]:
        # Explicit failure categories must never silently convert to success
        app_status = "FAILED"
    elif (inst_status in ["SUCCESS", "SUCCESS_VERSION_MISMATCH", "ALREADY_INSTALLED"]) and app.get("verification_status") in ["SUCCESS", "UNKNOWN", "SUCCESS_VERSION_MISMATCH"]:
        app_status = "SUCCESS"
        
        # Cache the successful research strategy
        try:
            from app.services.redis_service import redis_service
            from app.services.script_registry_service import ScriptRegistryService
            canonical_app = ScriptRegistryService.get_canonical_name(app_name)
            
            os_groups = state.get("os_groups", {})
            strategies = state.get("strategies", {})
            for sig in os_groups.keys():
                strategy = strategies.get(sig, {}).get(app_name)
                if strategy:
                    os_name = sig.split("_")[0]
                    architecture = sig.split("_")[-1] if "_" in sig else "unknown"
                    redis_service.set_research_result(
                        canonical_app, 
                        app.get("target_version", "latest"), 
                        os_name, 
                        architecture, 
                        strategy
                    )
                    broadcast_log(job_id, agent_name, f"[{sig}] Successfully cached research strategy for {canonical_app}")
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Failed to cache research strategy: {e}", "warning")
            
    elif inst_status == "ALREADY_INSTALLED" or (
            host_state in ["ALREADY_LATEST", "ALREADY_TARGET_VERSION", "NO_UPDATE_REQUIRED"]
            and app.get("failure_category") not in ["VERSION_DETECTION_FAILED", "APPLICATION_NOT_INSTALLED",
                                                     "STATE_CHECK_FAILED", "CURRENT_VERSION_UNKNOWN"]
            and app.get("status") != "FAILED"
            and state.get("status") != "FAILED"
        ) or (
            state.get("status") == "NO_UPDATE_REQUIRED"
            and app.get("failure_category") not in ["VERSION_DETECTION_FAILED", "APPLICATION_NOT_INSTALLED",
                                                     "STATE_CHECK_FAILED", "CURRENT_VERSION_UNKNOWN"]
            and app.get("status") != "FAILED"
        ):
        app_status = "ALREADY_INSTALLED" if inst_status == "ALREADY_INSTALLED" or (
            host_state != "NO_UPDATE_REQUIRED" and state.get("status") != "NO_UPDATE_REQUIRED"
        ) else "NO_UPDATE_REQUIRED"
        app["installation_status"] = app_status
        if "verification_status" not in app or app["verification_status"] == "UNKNOWN":
            app["verification_status"] = "SUCCESS"
    elif state.get("status") == "ARTIFACT_REQUIRED" or inst_status == "ARTIFACT_REQUIRED":
        app_status = "ARTIFACT_REQUIRED"
    elif state.get("status") == "UPDATE_REQUIRES_HUMAN_APPROVAL":
        app_status = "UPDATE_REQUIRES_HUMAN_APPROVAL"
    elif host_state == "VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST":
        app_status = "VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST"
    elif inst_status in ["FAILED", "FAILURE"] or app.get("verification_status") in ["FAILED", "FAILURE"] or state.get("status") == "FAILED":
        app_status = "FAILED"
    elif state.get("status") == "COMPLETED":
        app_status = "SUCCESS"
        if "installation_status" not in app:
            app["installation_status"] = "SUCCESS"
        if "verification_status" not in app:
            app["verification_status"] = "UNKNOWN"
            
    app["status"] = app_status
    app["target_version"] = state.get("target_version")
    
    # Authoritatively update underlying dictionaries to prevent auxiliary checks from showing FAILED
    installed_versions = state.get("installed_versions", {})
    if app_status in ["SUCCESS", "ALREADY_INSTALLED"]:
        for host_id in state.get("host_ids", []):
            if host_id not in app_states: app_states[host_id] = {}
            if host_id not in installed_versions: installed_versions[host_id] = {}
            app_states[host_id][app_name] = "INSTALLED"
            if app.get("installed_version"):
                installed_versions[host_id][app_name] = app.get("installed_version")
    
    import time
    app_end_time = time.time()
    app_start = state.get("application_start_time")
    
    research_start = state.get("research_start_time")
    research_end = state.get("research_end_time") or time.time() if research_start else None
    
    gen_start = state.get("script_generation_start_time")
    gen_end = state.get("script_generation_end_time") or time.time() if gen_start else None
    
    exec_start = state.get("fleet_execution_start_time")
    exec_end = state.get("fleet_execution_end_time") or time.time() if exec_start else None
    
    r_dur = (research_end - research_start) if research_start and research_end else 0
    g_dur = (gen_end - gen_start) if gen_start and gen_end else 0
    e_dur = (exec_end - exec_start) if exec_start and exec_end else 0
    
    app["research_duration"] = r_dur
    app["generation_duration"] = g_dur
    app["execution_duration"] = e_dur
    
    duration_str = ""
    if app_start:
        duration = app_end_time - app_start
        app["duration_seconds"] = duration
        duration_str = f" (Total: {duration:.1f}s | Res: {r_dur:.1f}s, Gen: {g_dur:.1f}s, Exec: {e_dur:.1f}s)"
        
    final_log = [
        f"\n[Application: {app_name}]",
        "[FINAL]",
        f"Installation: {inst_status}",
        f"Verification: {app.get('verification_status', 'UNKNOWN')}",
        f"Overall: {app_status}"
    ]
    for line in final_log:
        broadcast_log(job_id, agent_name, line)
        
    broadcast_log(job_id, agent_name, f"Finished processing app '{app_name}': Status={app_status}{duration_str}")
    
    applications[current_index] = app
    
    # If this was the last app, log a full deployment summary
    if current_index + 1 >= len(applications):
        summary = ["", "="*50, "DEPLOYIQ DEPLOYMENT SUMMARY", "="*50]
        total_duration = 0
        success_count = 0
        failed_count = 0
        for a in applications:
            d = a.get("duration_seconds", 0)
            rd = a.get("research_duration", 0)
            gd = a.get("generation_duration", 0)
            ed = a.get("execution_duration", 0)
            vd = 0 # verification is bundled in execution for now
            total_duration += d
            status = a.get("status", "UNKNOWN")
            if status in ["SUCCESS", "ALREADY_INSTALLED"]:
                success_count += 1
            else:
                failed_count += 1
                
            summary.append(f"Application: {a.get('name')}")
            summary.append(f"Status: {status}")
            summary.append(f"Research: {rd:.1f}s")
            summary.append(f"Script Generation: {gd:.1f}s")
            summary.append(f"Execution: {ed:.1f}s")
            summary.append(f"Verification: {vd:.1f}s")
            summary.append(f"Total: {d:.1f}s")
            summary.append("")
            
        overall = "SUCCESS" if failed_count == 0 else ("FAILED" if success_count == 0 else "PARTIAL_SUCCESS")
        summary.append(f"Overall Status: {overall}")
        summary.append(f"Total Applications: {len(applications)}")
        summary.append(f"Successful: {success_count}")
        summary.append(f"Failed: {failed_count}")
        summary.append(f"Total Deployment Time: {total_duration:.1f}s")
        summary.append("="*50)
        
        for line in summary:
            broadcast_log(job_id, agent_name, line)
    
    return {
        "applications": applications,
        "application_states": app_states,
        "installed_versions": installed_versions,
        "current_app_index": current_index + 1,
        # Re-initialize the active task status back to RUNNING for the next iteration
        "status": "RUNNING"
    }

def route_after_store_application_result(state: InstallationState):
    if _is_cancelled(state): return "notification"
    applications = state.get("applications", [])
    current_index = state.get("current_app_index", 0)
    if current_index < len(applications):
        return "prepare_current_application"
    return "notification"

from app.graph.nodes.installation_script_cleanup import installation_script_cleanup

def create_installation_graph():
    workflow = StateGraph(InstallationState)
    
    # Add nodes
    workflow.add_node("validation", validate_request)
    workflow.add_node("host_discovery", discover_hosts)
    workflow.add_node("os_detection", detect_os)
    
    # Sequential Loop Nodes
    workflow.add_node("prepare_current_application", prepare_current_application)
    workflow.add_node("store_application_result", store_application_result)
    
    # Application Installation Stages
    workflow.add_node("application_strategy_lookup", application_strategy_lookup)
    workflow.add_node("application_strategy_discovery", application_strategy_discovery)
    workflow.add_node("application_state_check", check_application_state)
    workflow.add_node("latest_version_discovery", latest_version_discovery)
    workflow.add_node("version_decision", version_decision)
    workflow.add_node("script_registry_lookup", script_registry_lookup)
    workflow.add_node("installation_research", installation_research)
    workflow.add_node("installation_research_validation", validate_installation_research)
    workflow.add_node("script_generation", generate_script)
    workflow.add_node("script_validation", validate_script)
    workflow.add_node("risk_analysis", analyze_risk)
    workflow.add_node("fleet_execution", execute_fleet)
    workflow.add_node("monitoring", monitor_execution)
    workflow.add_node("installation_script_cleanup", installation_script_cleanup)
    workflow.add_node("script_failure_analysis", analyze_script_failure)
    
    workflow.add_node("notification", send_notification)
    
    # Add edges
    workflow.set_entry_point("validation")
    
    workflow.add_conditional_edges("validation", route_after_validation, {"notification": "notification", "host_discovery": "host_discovery"})
    workflow.add_conditional_edges("host_discovery", route_after_host_discovery, {"notification": "notification", "os_detection": "os_detection"})
    workflow.add_conditional_edges("os_detection", route_after_os_detection, {"notification": "notification", "prepare_current_application": "prepare_current_application"})
    
    # Loop Entry Edge
    workflow.add_conditional_edges("prepare_current_application", route_after_prepare_current_application, {
        "notification": "notification",
        "application_strategy_lookup": "application_strategy_lookup"
    })
    
    # Conditional Edges for individual app flow
    workflow.add_conditional_edges("application_strategy_lookup", route_after_strategy_lookup, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "application_state_check": "application_state_check",
        "application_strategy_discovery": "application_strategy_discovery"
    })
    
    workflow.add_conditional_edges("application_strategy_discovery", route_after_strategy_discovery, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "application_state_check": "application_state_check"
    })
    
    workflow.add_conditional_edges("application_state_check", route_after_application_state_check, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "latest_version_discovery": "latest_version_discovery"
    })
    
    workflow.add_conditional_edges("latest_version_discovery", route_after_latest_version_discovery, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "version_decision": "version_decision"
    })
    
    workflow.add_conditional_edges("version_decision", route_after_version_decision, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "script_registry_lookup": "script_registry_lookup"
    })
    
    workflow.add_conditional_edges("script_registry_lookup", route_after_script_registry_lookup, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "script_generation": "script_generation",         # fast path (all scripts reused)
        "installation_research": "installation_research", # new path (at least one needs research)
    })

    workflow.add_conditional_edges("installation_research", route_after_installation_research, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "installation_research_validation": "installation_research_validation",
    })
    
    workflow.add_conditional_edges("installation_research_validation", route_after_installation_research_validation, {
        "notification": "notification",
        "installation_research": "installation_research",
        "store_application_result": "store_application_result",
        "script_generation": "script_generation",
    })
    
    workflow.add_conditional_edges("script_generation", route_after_script_generation, {
        "notification": "notification",
        "script_failure_analysis": "script_failure_analysis",
        "script_validation": "script_validation"
    })

    workflow.add_conditional_edges("script_validation", route_after_script_validation, {
        "notification": "notification",
        "script_failure_analysis": "script_failure_analysis",
        "risk_analysis": "risk_analysis"
    })
    
    workflow.add_conditional_edges("risk_analysis", route_after_risk_analysis, {
        "notification": "notification",
        "store_application_result": "store_application_result",
        "script_failure_analysis": "script_failure_analysis",
        "fleet_execution": "fleet_execution"
    })
    
    workflow.add_conditional_edges("fleet_execution", route_after_fleet_execution, {"monitoring": "monitoring"})
    
    workflow.add_edge("monitoring", "installation_script_cleanup")
    
    workflow.add_conditional_edges("installation_script_cleanup", route_after_installation_script_cleanup, {
        "script_failure_analysis": "script_failure_analysis",
        "store_application_result": "store_application_result"
    })
    
    workflow.add_conditional_edges("script_failure_analysis", route_after_script_failure_analysis, {
        "notification": "notification",
        "script_generation": "script_generation",
        "installation_research": "installation_research",
        "store_application_result": "store_application_result"
    })
    
    workflow.add_conditional_edges("store_application_result", route_after_store_application_result, {
        "notification": "notification",
        "prepare_current_application": "prepare_current_application"
    })
    
    workflow.add_edge("notification", END)
    
    return workflow.compile()

