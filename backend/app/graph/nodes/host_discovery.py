from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from app.services.agent_event_service import AgentEventService

def discover_hosts(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "HostDiscoveryAgent"
    stage_name = "HOST_DISCOVERY"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting Host Discovery")
    
    updates = {"current_stage": "HOST_DISCOVERY"}
    
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "FleetDM is disabled. Using configured mock host.")
        mock_id = settings.MOCK_HOST_ID
        updates["host_ids"] = [mock_id]
        
        broadcast_log(job_id, agent_name, f"Hosts discovered: {updates['host_ids']}")
        AgentEventService.broadcast_host_info(
            job_id=job_id,
            host_ids=updates["host_ids"],
            hostname="mocked-host"
        )
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return updates

    # FleetDM is the absolute source of truth for hosts
    existing_host_ids = state.get("host_ids", [])
    requested_host = None
    if existing_host_ids:
        requested_host = str(existing_host_ids[0]).strip()
    elif state.get("host_id"):
        requested_host = str(state.get("host_id")).strip()

    if not requested_host or requested_host in ("dynamic", "none", "null"):
        error_message = "No target host specified in request. A target host or IP must be provided."
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        
        requester_email = state.get("requester_email")
        if requester_email:
            from app.services.email_service import EmailService
            EmailService.send_host_not_found_email(
                recipient_email=requester_email,
                requested_host="unspecified host"
            )
        return {
            **updates,
            "status": "FAILED",
            "failure_category": "HOST_NOT_FOUND_IN_FLEET",
            "error_message": error_message
        }

    broadcast_log(job_id, agent_name, f"Verifying requested target host '{requested_host}' in FleetDM...")
    host_info = FleetDMService.verify_host_enrolled(requested_host)

    if not host_info:
        error_message = (
            f"The requested host '{requested_host}' was not found in FleetDM. "
            f"No installation/update was performed. "
            f"Please verify that the host is enrolled in FleetDM."
        )
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")

        # Notify original requester immediately
        requester_email = state.get("requester_email")
        if requester_email:
            from app.services.email_service import EmailService
            email_msg = state.get("email_message", {})
            in_reply_to = email_msg.get("message_id") if isinstance(email_msg, dict) else None
            EmailService.send_host_not_found_email(
                recipient_email=requester_email,
                requested_host=requested_host,
                in_reply_to=in_reply_to
            )

        return {
            **updates,
            "status": "FAILED",
            "failure_category": "HOST_NOT_FOUND_IN_FLEET",
            "error_message": error_message
        }

    resolved_host_id = int(host_info.get("id"))
    hostname = host_info.get("hostname", f"Host-{resolved_host_id}")

    broadcast_log(job_id, agent_name, f"Successfully verified host '{requested_host}' in FleetDM (ID: {resolved_host_id}, Hostname: {hostname})")
    updates["host_ids"] = [resolved_host_id]
    updates["hostname"] = hostname

    AgentEventService.broadcast_host_info(
        job_id=job_id,
        host_ids=updates["host_ids"],
        hostname=hostname
    )
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
