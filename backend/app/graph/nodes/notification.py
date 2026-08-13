import os
from datetime import datetime
from app.graph.state import InstallationState
from app.services.email_service import EmailService
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.database.database import SessionLocal
from app.database.repositories.job_repository import job_repo

def _send_email(state: InstallationState, job_id: str, agent_name: str) -> bool:
    broadcast_log(job_id, agent_name, "Sending installation email")
    
    app_name = f"{state.get('application_name')} (v{state.get('version')})"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    host_ids = state.get('host_ids')
    hostnames = ", ".join(str(h) for h in host_ids) if host_ids else "N/A"
    
    recipient_email = "rashmi.sahu@ap2l.ai"
    
    status = state.get("status")
    verification_result = state.get("verification_result")
    error_message = state.get("error_message")
    
    if status == "COMPLETED" and verification_result is True:
        success, msg = EmailService.send_installation_success(
            recipient_email=recipient_email,
            application_name=app_name,
            status="COMPLETED",
            timestamp=timestamp,
            hostname=hostnames
        )
    else:
        # The user requested NOT to send failure emails. Only send if successful.
        broadcast_log(job_id, agent_name, "Installation failed. Skipping failure email as per user request.")
        success = True
        msg = "Skipped failure email"
        
    if success:
        broadcast_log(job_id, agent_name, "Email sent successfully")
    else:
        broadcast_log(job_id, agent_name, f"Email failed to send: {msg}", "warning")
        
    return success

def _generate_audit_log_content(state: InstallationState, end_time: datetime) -> str:
    started_at = state.get("started_at")
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
            state_val = application_states.get(host_id, "N/A")
            inst_ver = installed_versions.get(host_id, "N/A")
            avail_ver = available_versions.get(host_id, "N/A")
            app_state_results += f"""Host {host_id}:
    State: {state_val}
    Installed Version: {inst_ver}
    Available Version: {avail_ver}
"""
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
    if final_status == "COMPLETED" and verification_result is False:
        final_status = "FAILED"
        
    reason = state.get("error_message") or "N/A"
    if final_status == "FAILED" and verification_result is False and not state.get("error_message"):
        reason = "Application Verification failed"
        
    email_status = "Sent" if state.get("email_sent", False) else "Failed/Not Sent"

    log_content = f"""============================================================
APPLICATION HUB INSTALLATION AUDIT
============================================================

Job ID: {state.get("job_id")}
Application: {state.get("application_name")}
Version: {state.get("version")}

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

    if state.get("status") == "CANCELLED":
        broadcast_log(job_id, agent_name, "Job was cancelled. Skipping email notification.")
        email_sent = False
        updates["email_sent"] = False
        updates["status"] = "CANCELLED"
    else:
        email_sent = _send_email(state, job_id, agent_name)
        updates["email_sent"] = email_sent
    
    temp_state = dict(state)
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
    
    # If the workflow finished naturally and verification succeeded but status is still running/pending
    final_status = state.get("status")
    if final_status in ["PENDING", "RUNNING"] and state.get("verification_result") is True:
        updates["status"] = "COMPLETED"
        
    AgentEventService.broadcast_installation_complete(
        job_id=job_id,
        status=updates.get("status", final_status),
        error=updates.get("error_message", state.get("error_message"))
    )
        
    return updates
