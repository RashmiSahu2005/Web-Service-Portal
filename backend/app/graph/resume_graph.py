from langgraph.graph import StateGraph, END
from app.graph.state import InstallationState
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.script_generation import generate_script
from app.graph.nodes.script_validation import validate_script
from app.graph.nodes.risk_analysis import analyze_risk
from app.graph.nodes.fleet_execution import execute_fleet
from app.graph.nodes.monitoring import monitor_execution
from app.graph.nodes.installation_script_cleanup import installation_script_cleanup
from app.graph.nodes.script_failure_analysis import analyze_script_failure
from app.graph.nodes.notification import send_notification
from app.graph.graph import (
    prepare_current_application,
    store_application_result,
    route_after_script_generation,
    route_after_script_validation,
    route_after_risk_analysis,
    route_after_fleet_execution,
    route_after_installation_script_cleanup,
    route_after_script_failure_analysis
)

def create_resume_update_graph():
    workflow = StateGraph(InstallationState)
    
    workflow.add_node("prepare_current_application", prepare_current_application)
    workflow.add_node("application_state_check", check_application_state)
    
    def resume_update_validation(state: InstallationState):
        from app.graph.nodes.utils import broadcast_log
        from app.services.fleetdm_service import FleetDMService
        from app.core.config import settings
        from app.database.database import SessionLocal
        from app.database.repositories.approval_repository import approval_repo
        
        job_id = state.get("job_id", "")
        agent_name = "ResumeUpdateValidation"
        broadcast_log(job_id, agent_name, "Re-evaluating target host and approval state after authorization...")

        # 1. Re-check FleetDM host enrollment
        host_ids = state.get("host_ids", [])
        if not host_ids:
            broadcast_log(job_id, agent_name, "No target host specified for approved update.", "error")
            return {"status": "FAILED", "failure_category": "HOST_NOT_FOUND_IN_FLEET"}
        
        host_id = host_ids[0]
        if settings.USE_FLEETDM:
            host_info = FleetDMService.verify_host_enrolled(str(host_id))
            if not host_info:
                broadcast_log(job_id, agent_name, f"Host {host_id} is no longer enrolled in FleetDM.", "error")
                return {"status": "FAILED", "failure_category": "HOST_NOT_FOUND_IN_FLEET"}

        # 2. Re-check approval record in database
        db = SessionLocal()
        try:
            approvals = approval_repo.get_by_job_id(db, job_id) if hasattr(approval_repo, "get_by_job_id") else []
            if not approvals:
                # Query all approvals for job
                from app.database.models.approval import ApprovalRequest
                approvals = db.query(ApprovalRequest).filter(ApprovalRequest.job_id == job_id).all()
            if approvals and all(a.status != "APPROVED" for a in approvals):
                broadcast_log(job_id, agent_name, "Approval is no longer valid or was revoked. Halting execution.", "error")
                return {"status": "FAILED", "failure_category": "APPROVAL_REVOKED"}
        finally:
            db.close()

        # 3. Re-check installed application/version
        apps = state.get("applications", [])
        if not apps:
            return {"status": "FAILED", "failure_category": "APPLICATION_NOT_FOUND"}
            
        app = apps[0]
        installed = state.get("installed_versions", {}).get(host_id, {}).get(app.get("name"))
        
        if installed and installed == app.get("target_version"):
            broadcast_log(job_id, agent_name, "Target version is already installed! No update needed.")
            return {"status": "NO_UPDATE_REQUIRED"}
            
        return {"status": "RESUME_VALIDATED"}

    workflow.add_node("resume_update_validation", resume_update_validation)
    
    workflow.add_node("script_generation", generate_script)
    workflow.add_node("script_validation", validate_script)
    workflow.add_node("risk_analysis", analyze_risk)
    workflow.add_node("fleet_execution", execute_fleet)
    workflow.add_node("monitoring", monitor_execution)
    workflow.add_node("installation_script_cleanup", installation_script_cleanup)
    workflow.add_node("script_failure_analysis", analyze_script_failure)
    workflow.add_node("store_application_result", store_application_result)
    workflow.add_node("notification", send_notification)
    
    workflow.set_entry_point("prepare_current_application")
    workflow.add_edge("prepare_current_application", "application_state_check")
    workflow.add_edge("application_state_check", "resume_update_validation")
    
    def route_after_resume(state: InstallationState):
        if state.get("status") == "NO_UPDATE_REQUIRED":
            return "store_application_result"
        return "script_generation"
        
    workflow.add_conditional_edges("resume_update_validation", route_after_resume, {
        "store_application_result": "store_application_result",
        "script_generation": "script_generation"
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
        "store_application_result": "store_application_result"
    })
    
    workflow.add_edge("store_application_result", "notification")
    workflow.add_edge("notification", END)
    
    return workflow.compile()
