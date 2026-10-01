import os
from datetime import datetime
from app.graph.state import InstallationState
from app.services.email_service import EmailService
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.database.database import SessionLocal
from app.database.repositories.job_repository import job_repo

def _send_email(state: InstallationState, job_id: str, agent_name: str) -> bool:
    broadcast_log(job_id, agent_name, "Sending installation report email")
    
    applications = state.get("applications", [])
    
    success_count = sum(1 for a in applications if a.get("status") in ["SUCCESS", "ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"])
    failed_count = sum(1 for a in applications if a.get("status") not in ["SUCCESS", "ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"])
    
    if failed_count > 0 and success_count == 0:
        overall_status = "FAILED"
    elif failed_count > 0 and success_count > 0:
        overall_status = "PARTIAL_SUCCESS"
    else:
        overall_status = "SUCCESS"
        
    summary_lines = []
    for a in applications:
        app_name = a.get("name") or a.get("application_name")
        status_val = a.get("status", "FAILED")
        summary_lines.append(f"{app_name:<20} - {status_val}")
        
    summary_text = "\n".join(summary_lines)
    
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    host_ids = state.get('host_ids')
    hostnames = ", ".join(str(h) for h in host_ids) if host_ids else "N/A"
    
    recipient_email = state.get("requester_email")
    if not recipient_email:
        broadcast_log(job_id, agent_name, "No requester_email found in state! Cannot send notification.", "error")
        return False
        
    success, msg = EmailService.send_multi_app_report(
        recipient_email=recipient_email,
        summary_text=summary_text,
        overall_status=overall_status,
        timestamp=timestamp,
        hostname=hostnames
    )
    
    if success:
        broadcast_log(job_id, agent_name, "Email report sent successfully")
    else:
        broadcast_log(job_id, agent_name, f"Email report failed to send: {msg}", "warning")
        
    return success

def _generate_audit_log_content(state: InstallationState, end_time: datetime) -> str:
    started_at = state.get("started_at")
    if isinstance(started_at, (int, float)):
        started_at = datetime.fromtimestamp(started_at)
    started_at_str = started_at.strftime("%Y-%m-%d %H:%M:%S UTC") if started_at else "N/A"
    duration = str(end_time - started_at) if started_at else "N/A"
    
    risk_reasons = state.get("risk_reasons")
    risk_reasons_str = "\n".join(f"- {r}" for r in risk_reasons) if risk_reasons else "N/A"
    
    host_ids = state.get("host_ids", [])
    execution_ids = state.get("execution_ids", [])
    verification_results = state.get("verification_results", {})
    
    application_states = state.get("application_states", {})
    installed_versions = state.get("installed_versions", {})
    available_versions = state.get("available_versions", {})
    
    app_state_results = ""
    if host_ids:
        for host_id in host_ids:
            app_state_results += f"Host {host_id}:\n"
            host_states = application_states.get(host_id, {})
            host_versions = installed_versions.get(host_id, {})
            if isinstance(host_states, dict):
                for app_name, state_val in host_states.items():
                    inst_ver = host_versions.get(app_name, "N/A")
                    app_state_results += f"    {app_name}: State={state_val}, Installed={inst_ver}\n"
            else:
                app_state_results += f"    State: {host_states}\n"

    else:
        app_state_results = "N/A\n"
        
    host_results = ""
    if host_ids:
        for i, host_id in enumerate(host_ids):
            exec_id = execution_ids[i] if i < len(execution_ids) else "N/A"
            verif = verification_results.get(host_id, "N/A")
            host_results += f"""
Host {host_id}:
    Execution ID: {exec_id}
    Verification: {verif}
"""
    else:
        host_results = "N/A"
        
    verification_result = state.get("verification_result")
    verif_overall = "VERIFIED" if verification_result is True else ("FAILED" if verification_result is False else "N/A")
    
    final_status = state.get("status", "UNKNOWN")
    # DO NOT mutate final_status to FAILED here. Installation succeeded.
    if final_status == "COMPLETED" and verification_result is False:
        final_status = "COMPLETED_WITH_VERIFICATION_WARNING"
        
    reason = state.get("error_message") or "N/A"
    if final_status == "COMPLETED_WITH_VERIFICATION_WARNING":
        reason = "Installation succeeded but verification check failed."
        
    email_status = "Sent" if state.get("email_sent", False) else "Failed/Not Sent"

    log_content = f"""============================================================
DEPLOYIQ INSTALLATION AUDIT
============================================================

Job ID: {state.get("job_id")}
Applications: {", ".join([a.get('name') or a.get('application_name', '') for a in state.get('applications', [])])}

Started At: {started_at_str}
Completed At: {end_time.strftime("%Y-%m-%d %H:%M:%S UTC")}
Duration: {duration}
Final Status: {final_status}

------------------------------------------------------------
HOST
------------------------------------------------------------
Host IDs: {', '.join(str(h) for h in host_ids) if host_ids else 'N/A'}

------------------------------------------------------------
APPLICATION STATE
------------------------------------------------------------
{app_state_results}
------------------------------------------------------------
SCRIPT GENERATION & REGISTRY
------------------------------------------------------------
Script Generation Type: {'REUSED_EXISTING' if state.get('script_reused') else 'GENERATED_NEW'}
Registry ID: {state.get('script_registry_id') or 'N/A'}
Script Generated: {'Yes' if state.get("script_content") else 'No'}
Script SHA-256: {state.get("script_hash") or 'N/A'}

------------------------------------------------------------
RISK ANALYSIS
------------------------------------------------------------
Risk Score: {state.get("risk_score")}
Risk Level: {state.get("risk_level") or 'N/A'}

Risk Reasons:
{risk_reasons_str}

------------------------------------------------------------
FLEETDM EXECUTION
------------------------------------------------------------
Fleet Script ID: {state.get("fleet_script_id") or 'N/A'}
Execution IDs: {', '.join(execution_ids) if execution_ids else 'N/A'}
Installation Cleanup Status: {state.get("installation_script_deleted")}
Cleanup Errors: {state.get("installation_cleanup_error")}

Host Execution Results:
{host_results}
------------------------------------------------------------
VERIFICATION
------------------------------------------------------------
Overall Verification: {verif_overall}
Verification Script IDs: {state.get("verification_fleet_script_ids")}
Verification Execution IDs: {', '.join(state.get("verification_execution_ids", []))}
Verification Cleanup Status: {state.get("verification_script_deleted")}
Verification Cleanup Errors: {state.get("verification_cleanup_error")}

------------------------------------------------------------
NOTIFICATION
------------------------------------------------------------
Email Status: {email_status}

------------------------------------------------------------
FINAL RESULT
------------------------------------------------------------
Status: {final_status}
Failure Reason: {reason}

============================================================
"""
    return log_content

def _write_audit_log(state: InstallationState, job_id: str, agent_name: str):
    broadcast_log(job_id, agent_name, "Creating audit log")
    
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y%m%d_%H%M%S")
    
    logs_base_dir = os.environ.get("AUDIT_LOGS_DIR", os.path.join(os.getcwd(), "logs"))
    date_dir = os.path.join(logs_base_dir, date_str)
    
    os.makedirs(date_dir, exist_ok=True)
    
    filename = f"{time_str}_job_{job_id}.log"
    filepath = os.path.join(date_dir, filename)
    
    content = _generate_audit_log_content(state, now)
    
    with open(filepath, "w") as f:
        f.write(content)
        
    broadcast_log(job_id, agent_name, f"Audit log created: {filepath}")

async def send_notification(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "NotificationAgent"
    stage_name = "EMAIL_NOTIFICATION"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting notification")
    
    updates = {}
    
    # Sync with DB to catch cancellation during graph execution
    db = SessionLocal()
    try:
        job = job_repo.get(db, job_id)
        if job and job.status == "CANCELLED":
            state["status"] = "CANCELLED"
            state["is_cancelled"] = True
    finally:
        db.close()

    # Calculate overall status
    applications = state.get("applications", [])
    success_count = sum(1 for a in applications if a.get("status") in ["SUCCESS", "ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"])
    failed_count = sum(1 for a in applications if a.get("status") not in ["SUCCESS", "ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"])
    
    if failed_count > 0 and success_count == 0:
        overall_status = "FAILED"
    elif failed_count > 0 and success_count > 0:
        overall_status = "PARTIAL_SUCCESS"
    else:
        overall_status = "SUCCESS"

    if state.get("status") == "CANCELLED":
        broadcast_log(job_id, agent_name, "Job was cancelled. Skipping email notification.")
        email_sent = False
        updates["email_sent"] = False
        updates["status"] = "CANCELLED"
        overall_status = "CANCELLED"
    else:
        email_sent = _send_email(state, job_id, agent_name)
        updates["email_sent"] = email_sent
        updates["status"] = overall_status
    
    temp_state = dict(state)
    temp_state["status"] = overall_status
    temp_state["email_sent"] = email_sent
    _write_audit_log(temp_state, job_id, agent_name)
    
    if email_sent:
        updates["current_stage"] = "NOTIFICATION_SENT"
        AgentEventService.broadcast_notification_status(
            job_id=job_id,
            email_sent=True,
            status="COMPLETED"
        )
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    else:
        updates["error_message"] = "Failed to send installation email."
        AgentEventService.broadcast_notification_status(
            job_id=job_id,
            email_sent=False,
            status="FAILED"
        )
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        
    now = datetime.utcnow()
    updates["completed_at"] = now
    
    AgentEventService.broadcast_installation_complete(
        job_id=job_id,
        status=overall_status,
        error=updates.get("error_message", state.get("error_message"))
    )
        
    return updates
