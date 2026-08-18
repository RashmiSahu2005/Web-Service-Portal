# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END
from app.graph.state import InstallationState

from app.graph.nodes.validation import validate_request
from app.graph.nodes.host_discovery import discover_hosts
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.script_registry_lookup import script_registry_lookup
from app.graph.nodes.script_generation import generate_script
from app.graph.nodes.risk_analysis import analyze_risk
from app.graph.nodes.fleet_execution import execute_fleet
from app.graph.nodes.monitoring import monitor_execution
from app.graph.nodes.script_failure_analysis import analyze_script_failure
from app.graph.nodes.verification import verify_installation
from app.graph.nodes.notification import send_notification
from app.graph.nodes.os_detection import detect_os
from app.graph.nodes.application_strategy_lookup import application_strategy_lookup
from app.graph.nodes.application_strategy_discovery import application_strategy_discovery

from app.database.database import SessionLocal
from app.database.repositories.job_repository import job_repo

def _is_cancelled_or_failed(state: InstallationState):
    if state.get("is_cancelled") or state.get("status") == "CANCELLED":
        return True
    if state.get("status") == "FAILED":
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
    if _is_cancelled_or_failed(state): return "notification"
    return "host_discovery"

def route_after_host_discovery(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "os_detection"

def route_after_os_detection(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "application_strategy_lookup"

def route_after_strategy_lookup(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    
    os_groups = state.get("os_groups", {})
    strategy_reused = state.get("strategy_reused", {})
    
    if os_groups and all(strategy_reused.get(sig, False) for sig in os_groups):
        return "application_state_check"
    return "application_strategy_discovery"

def route_after_strategy_discovery(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "application_state_check"

from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.version_decision import version_decision

def route_after_application_state_check(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "latest_version_discovery"

def route_after_latest_version_discovery(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "version_decision"

def route_after_version_decision(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    
    hosts_requiring_installation = state.get("hosts_requiring_installation", [])
    if not hosts_requiring_installation:
        # All hosts are ALREADY_LATEST (or similar), no installation required
        return "notification"
        
    return "script_registry_lookup"

def route_after_script_registry_lookup(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    # We no longer reuse scripts directly for FleetDM, so always go to script_generation
    return "script_generation"

def route_after_script_generation(state: InstallationState):
    if _is_cancelled_or_failed(state): return "notification"
    return "risk_analysis"

def route_after_risk_analysis(state: InstallationState):
    if _is_cancelled_or_failed(state) or state.get("status") == "BLOCKED_HIGH_RISK":
        return "notification"
    return "fleet_execution"

def route_after_fleet_execution(state: InstallationState):
    # Always go to monitoring so it can transition to cleanup even if execution failed
    return "monitoring"

def route_after_script_failure_analysis(state: InstallationState):
    if state.get("status") == "SCRIPT_REGENERATION_TRIGGERED":
        return "script_generation"
    if _is_cancelled_or_failed(state): return "notification"
    return "verification_script_generation"

from app.graph.nodes.installation_script_cleanup import installation_script_cleanup
from app.graph.nodes.verification_script_generation import verification_script_generation
from app.graph.nodes.verification_execution import verification_execution
from app.graph.nodes.verification_monitoring import verification_monitoring
from app.graph.nodes.verification_script_cleanup import verification_script_cleanup

def create_installation_graph():
    workflow = StateGraph(InstallationState)
    
    # Add nodes
    workflow.add_node("validation", validate_request)
    workflow.add_node("host_discovery", discover_hosts)
    workflow.add_node("os_detection", detect_os)
    workflow.add_node("application_strategy_lookup", application_strategy_lookup)
    workflow.add_node("application_strategy_discovery", application_strategy_discovery)
    workflow.add_node("application_state_check", check_application_state)
    workflow.add_node("latest_version_discovery", latest_version_discovery)
    workflow.add_node("version_decision", version_decision)
    workflow.add_node("script_registry_lookup", script_registry_lookup)
    workflow.add_node("script_generation", generate_script)
    workflow.add_node("risk_analysis", analyze_risk)
    workflow.add_node("fleet_execution", execute_fleet)
    workflow.add_node("monitoring", monitor_execution)
    workflow.add_node("installation_script_cleanup", installation_script_cleanup)
    workflow.add_node("script_failure_analysis", analyze_script_failure)
    
    workflow.add_node("verification_script_generation", verification_script_generation)
    workflow.add_node("verification_execution", verification_execution)
    workflow.add_node("verification_monitoring", verification_monitoring)
    workflow.add_node("verification_script_cleanup", verification_script_cleanup)
    
    workflow.add_node("notification", send_notification)
    
    # Add edges
    workflow.set_entry_point("validation")
    
    workflow.add_conditional_edges("validation", route_after_validation, {"notification": "notification", "host_discovery": "host_discovery"})
    workflow.add_conditional_edges("host_discovery", route_after_host_discovery, {"notification": "notification", "os_detection": "os_detection"})
    workflow.add_conditional_edges("os_detection", route_after_os_detection, {"notification": "notification", "application_strategy_lookup": "application_strategy_lookup"})
    
    workflow.add_conditional_edges("application_strategy_lookup", route_after_strategy_lookup, {
        "notification": "notification",
        "application_state_check": "application_state_check",
        "application_strategy_discovery": "application_strategy_discovery"
    })
    
    workflow.add_conditional_edges("application_strategy_discovery", route_after_strategy_discovery, {
        "notification": "notification",
        "application_state_check": "application_state_check"
    })
    
    workflow.add_conditional_edges("application_state_check", route_after_application_state_check, {
        "notification": "notification",
        "latest_version_discovery": "latest_version_discovery",
        "version_decision": "version_decision"
    })
    
    workflow.add_conditional_edges("latest_version_discovery", route_after_latest_version_discovery, {
        "notification": "notification",
        "version_decision": "version_decision"
    })
    
    workflow.add_conditional_edges("version_decision", route_after_version_decision, {
        "notification": "notification",
        "script_registry_lookup": "script_registry_lookup"
    })
    
    workflow.add_conditional_edges("script_registry_lookup", route_after_script_registry_lookup, {
        "notification": "notification",
        "script_generation": "script_generation"
    })
    
    workflow.add_conditional_edges("script_generation", route_after_script_generation, {"notification": "notification", "risk_analysis": "risk_analysis"})
    workflow.add_conditional_edges("risk_analysis", route_after_risk_analysis, {"notification": "notification", "fleet_execution": "fleet_execution"})
    
    workflow.add_conditional_edges("fleet_execution", route_after_fleet_execution, {"monitoring": "monitoring"})
    
    workflow.add_edge("monitoring", "installation_script_cleanup")
    workflow.add_edge("installation_script_cleanup", "script_failure_analysis")
    
    workflow.add_conditional_edges("script_failure_analysis", route_after_script_failure_analysis, {
        "notification": "notification",
        "script_generation": "script_generation",
        "verification_script_generation": "verification_script_generation"
    })
    
    # Verification flow is linear, skipping internal logic if status is FAILED
    workflow.add_edge("verification_script_generation", "verification_execution")
    workflow.add_edge("verification_execution", "verification_monitoring")
    workflow.add_edge("verification_monitoring", "verification_script_cleanup")
    workflow.add_edge("verification_script_cleanup", "notification")
    
    workflow.add_edge("notification", END)
    
    return workflow.compile()
