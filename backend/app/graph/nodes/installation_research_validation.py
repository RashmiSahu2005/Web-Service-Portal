from app.graph.state import InstallationState
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def validate_installation_research(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "InstallationResearchValidationAgent"
    stage_name = "INSTALLATION_RESEARCH_VALIDATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Validating installation research results...")
    
    research_results = state.get("research_results", {})
    os_groups = state.get("os_groups", {})
    script_reused_map = state.get("script_reused", {})
    current_status = state.get("status")
    operation = state.get("operation", "INSTALL")
    
    if current_status in ["RESEARCH_ERROR", "RESEARCH_INSUFFICIENT"]:
        research_attempts = state.get("research_attempts", {})
        max_research_attempts = state.get("max_research_attempts", {})
        attempt_summary = ", ".join(
            f"{sig}={v}/{max_research_attempts.get(sig, 3)}"
            for sig, v in research_attempts.items()
        ) or "no attempts recorded"
        broadcast_log(
            job_id, agent_name,
            f"Prior research node reported {current_status}. "
            f"Research attempts so far: [{attempt_summary}]. "
            f"Routing decision will be made by graph."
        )
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {"status": current_status}
    
    failed_any = False
    error_messages = []
    
    for sig in os_groups.keys():
        if script_reused_map.get(sig, False):
            continue
            
        research = research_results.get(sig, {})
        if not research:
            failed_any = True
            error = f"[{sig}] Missing research results."
            broadcast_log(job_id, agent_name, error, "error")
            error_messages.append(error)
            continue
            
        # Check research status
        status = research.get("research_status", "RESEARCH_SUCCESS")
        if status in ["RESEARCH_ERROR", "RESEARCH_INSUFFICIENT", "FAILED"]:
            failed_any = True
            error = f"[{sig}] Research status is {status}."
            broadcast_log(job_id, agent_name, error, "error")
            error_messages.append(error)
            continue
            
        # Pre-flight checklist for Research
        method = research.get("recommended_method", "").lower()
        if not method or method == "unknown":
            failed_any = True
            error = f"[{sig}] Unknown recommended_method in research."
            broadcast_log(job_id, agent_name, error, "error")
            error_messages.append(error)
            continue
            
        # Check critical actionable evidence based on normalized method
        if operation == "UPDATE" and research.get("update_requires_removal"):
            broadcast_log(job_id, agent_name, f"[{sig}] Research indicates the update requires application removal/replacement. Setting UPDATE_REQUIRES_HUMAN_APPROVAL.", "warning")
            
            app_name = state.get("application_name")
            target_version = state.get("target_version")
            
            from app.database.database import SessionLocal
            from app.database.repositories.approval_repository import approval_repo
            from app.database.models.approval import ApprovalRequest
            from app.services.email_service import EmailService
            
            db = SessionLocal()
            try:
                # Create an ApprovalRequest for each host in this OS group
                for host_id in os_groups.get(sig, []):
                    current_version = state.get("installed_versions", {}).get(host_id, {}).get(app_name, "Unknown")
                    original_requester = state.get("requester_email") or ""
                    original_message_id = state.get("original_message_id", "")
                    original_thread_id = state.get("original_thread_id", "")
                    
                    req = ApprovalRequest(
                        job_id=job_id,
                        application=app_name,
                        host_id=str(host_id),
                        hostname=str(host_id), # Hostname could be retrieved if needed
                        original_requester_email=original_requester,
                        original_message_id=original_message_id,
                        original_thread_id=original_thread_id,
                        current_version=current_version,
                        target_version=target_version,
                        approval_reason="The researched update path requires removal/replacement of the existing installation.",
                        os_signature=sig,
                        update_strategy=research
                    )
                    approval_repo.create(db, req)
                    
                    success, msg = EmailService.send_admin_approval_request(
                        application_name=app_name,
                        hostname=str(host_id),
                        current_version=current_version,
                        target_version=target_version,
                        approval_reason="The researched update path requires removal/replacement of the existing installation.",
                        planned_action=f"Uninstall/replace the existing installation and install version {target_version}.",
                        risk="The currently installed application may be temporarily removed during the update. User configuration/data impact, if applicable, must be stated.",
                        original_requester_email=original_requester,
                        original_message_id=original_message_id,
                        approval_id=req.id
                    )
                    
                    if success:
                        if msg and msg != "SMTP disabled":
                            req.admin_message_id = msg
                            approval_repo.update(db, req)
                            
                        ui_message = (
                            f"UPDATE BLOCKED - ADMIN APPROVAL REQUIRED\n"
                            f"Application: {app_name}\n"
                            f"Current version: {current_version}\n"
                            f"Target version: {target_version}\n"
                            f"Host: {host_id}\n"
                            f"Risk: The currently installed application may be temporarily removed during the update.\n"
                            f"Why approval is required: The researched update path requires removal/replacement of the existing installation.\n"
                            f"Approval status: PENDING\n"
                            f"Approval request ID: {req.id}"
                        )
                        broadcast_log(job_id, agent_name, ui_message, "warning")
                        broadcast_log(job_id, agent_name, "Approval email sent to admin")
                        broadcast_log(job_id, agent_name, "Waiting for admin approval")
                    else:
                        broadcast_log(job_id, agent_name, f"Failed to send approval email: {msg}", "error")
            finally:
                db.close()
                
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {"status": "UPDATE_REQUIRES_HUMAN_APPROVAL", "error_message": f"[{sig}] Update requires removal/replacement which requires explicit human approval."}

            
        # Normalize strategy for validation purposes
        normalized_strategy = "UNKNOWN"
        if method in ["apt", "rpm", "yum", "dnf", "pacman", "zypper", "repository", "package_manager"]:
            normalized_strategy = "PACKAGE_MANAGER"
        elif method in ["snap"]:
            normalized_strategy = "SNAP"
        elif method in ["flatpak"]:
            normalized_strategy = "FLATPAK"
        elif method in ["official_deb", "official_rpm", "tarball", "binary", "official_tarball", "zip"]:
            normalized_strategy = "DIRECT_ARTIFACT"
            
        # Check critical actionable evidence based on normalized method
        if normalized_strategy == "PACKAGE_MANAGER":
            if not research.get("package_name") and not research.get("installation_command"):
                failed_any = True
                error = f"[{sig}] For package manager '{method}', missing both package_name and installation_command."
                error_messages.append(error)
        elif normalized_strategy == "DIRECT_ARTIFACT":
            if not research.get("artifact_url") or not research.get("artifact_url_verified"):
                broadcast_log(job_id, agent_name, f"[{sig}] '{method}' requires an exact, verified artifact_url. None provided. Setting ARTIFACT_REQUIRED.", "warning")
                # Intercept immediately and return ARTIFACT_REQUIRED
                broadcast_stage(job_id, agent_name, stage_name, "FAILED")
                return {"status": "ARTIFACT_REQUIRED", "error_message": f"[{sig}] Method '{method}' requires a deterministic verified artifact_url. Generic download pages are insufficient."}
        elif research.get("artifact_required"):
            broadcast_log(job_id, agent_name, f"[{sig}] Research reported artifact_required=True.", "warning")
            broadcast_stage(job_id, agent_name, stage_name, "FAILED")
            return {"status": "ARTIFACT_REQUIRED", "error_message": f"[{sig}] Research indicates a user-supplied artifact is required."}
        
        # Check verification method
        if not research.get("verification_method") and not research.get("verification_command"):
            failed_any = True
            error = f"[{sig}] Missing verification_method and verification_command."
            error_messages.append(error)
            
        if error_messages:
            for error in error_messages:
                broadcast_log(job_id, agent_name, error, "error")

    if failed_any:
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {"status": "RESEARCH_INSUFFICIENT", "error_message": "; ".join(error_messages)}
        
    broadcast_log(job_id, agent_name, "Installation research validation passed successfully. All critical checklist items verified.")
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return {"current_stage": "INSTALLATION_RESEARCH_VALIDATED"}
