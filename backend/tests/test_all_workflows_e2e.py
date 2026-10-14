import pytest
import uuid
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from app.graph.email.graph import create_email_intake_graph
from app.graph.email.state import EmailState
from app.graph.state import InstallationState
from app.core.config import settings
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.version_decision import version_decision
from app.graph.nodes.monitoring import monitor_execution
from app.graph.nodes.notification import send_notification


# ==============================================================================
# WORKFLOW 1: Email Intake -> Validation -> Incident Generation -> Admin Approval
# ==============================================================================
def test_workflow_1_email_intake_and_approval_gate():
    """Test receiving an installation email request, validating host, and creating approval request."""
    graph = create_email_intake_graph()
    msg_id = f"<test-{uuid.uuid4()}@domain.com>"
    
    state = EmailState(
        message_id=msg_id,
        in_reply_to=None,
        references=[],
        subject="Install curl on 192.168.10.53",
        body="Please install curl on host 192.168.10.53",
        sender="engineer@company.com",
        status="RECEIVED"
    )
    
    with patch("app.services.fleetdm_service.FleetDMService.verify_host_enrolled", return_value={"id": 192, "hostname": "APMOSYSLT1200"}), \
         patch("app.services.email_service.EmailService.send_initial_approval_request", return_value=(True, "Sent")) as mock_send_approval, \
         patch("app.database.database.SessionLocal"):
        
        result = graph.invoke(state)
        
        assert result.get("status") == "PENDING_APPROVAL"
        assert result.get("application_name") == "curl"
        assert result.get("host_id") == "192"
        assert "incident_id" in result
        assert result["incident_id"].startswith("INC-")
        mock_send_approval.assert_called_once()


# ==============================================================================
# WORKFLOW 2: Admin Approval Reply -> Job Dispatch
# ==============================================================================
def test_workflow_2_admin_approval_and_job_dispatch():
    """Test an admin approving the request, transitioning to COMPLETED (job queued)."""
    import redis
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    graph = create_email_intake_graph()
    incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
    orig_msg_id = f"<orig-{uuid.uuid4()}@domain.com>"
    
    # Store pending state in Redis
    pending_state = {
        "message_id": orig_msg_id,
        "incident_id": incident_id,
        "sender": "engineer@company.com",
        "requester_email": "engineer@company.com",
        "application_name": "curl",
        "applications": [{"name": "curl", "version": "latest", "operation": "INSTALL"}],
        "target_host_ip": "192.168.10.53",
        "host_id": "192",
        "status": "PENDING_APPROVAL"
    }
    r.set(f"incident:{incident_id}", json.dumps(pending_state), ex=300)
    
    # Admin replies to approve
    reply_msg_id = f"<reply-{uuid.uuid4()}@domain.com>"
    reply_state = EmailState(
        message_id=reply_msg_id,
        in_reply_to=orig_msg_id,
        references=[orig_msg_id],
        subject=f"Re: [DeployIQ Approval Request] Incident {incident_id}",
        body="Approved. Proceed with installation.",
        sender=settings.APPROVAL_REQUEST_EMAILS[0] if settings.APPROVAL_REQUEST_EMAILS else (settings.ADMIN_APPROVAL_EMAILS[0] if settings.ADMIN_APPROVAL_EMAILS else "admin@domain.com"),
        status="RECEIVED"
    )
    
    with patch("app.database.database.SessionLocal"), \
         patch("app.services.installation_service.InstallationService.create_and_start_installation", return_value="job_test_12345") as mock_start:
        
        result = graph.invoke(reply_state)
        
        assert result.get("status") == "COMPLETED"
        assert result.get("job_id") == "job_test_12345"
        mock_start.assert_called_once()
    
    r.delete(f"incident:{incident_id}")


# ==============================================================================
# WORKFLOW 3: Admin Rejection Reply
# ==============================================================================
def test_workflow_3_admin_rejection():
    """Test admin rejecting an installation request."""
    import redis
    r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    graph = create_email_intake_graph()
    incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
    orig_msg_id = f"<orig-{uuid.uuid4()}@domain.com>"
    
    pending_state = {
        "message_id": orig_msg_id,
        "incident_id": incident_id,
        "sender": "engineer@company.com",
        "requester_email": "engineer@company.com",
        "application_name": "curl",
        "applications": [{"name": "curl", "version": "latest", "operation": "INSTALL"}],
        "target_host_ip": "192.168.10.53",
        "host_id": "192",
        "status": "PENDING_APPROVAL"
    }
    r.set(f"incident:{incident_id}", json.dumps(pending_state), ex=300)
    
    reply_state = EmailState(
        message_id=f"<reply-{uuid.uuid4()}@domain.com>",
        in_reply_to=orig_msg_id,
        references=[orig_msg_id],
        subject=f"Re: [DeployIQ Approval Request] Incident {incident_id}",
        body="Rejected. Do not install.",
        sender=settings.APPROVAL_REQUEST_EMAILS[0] if settings.APPROVAL_REQUEST_EMAILS else (settings.ADMIN_APPROVAL_EMAILS[0] if settings.ADMIN_APPROVAL_EMAILS else "admin@domain.com"),
        status="RECEIVED"
    )
    
    with patch("app.database.database.SessionLocal"):
        result = graph.invoke(reply_state)
        assert result.get("status") == "REJECTED"
        
    r.delete(f"incident:{incident_id}")


# ==============================================================================
# WORKFLOW 4: Application Already Installed Flow (No redundant execution)
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_4_already_installed_flow():
    """Test already-installed detection bypasses installation and marks ALREADY_INSTALLED."""
    app_dict = {"name": "docker", "version": "latest", "operation": "INSTALL"}
    state = InstallationState(
        job_id="job_already_installed_test",
        application_name="docker",
        version="latest",
        applications=[app_dict],
        host_ids=[192],
        os_groups={"Ubuntu_amd64": [192]},
        strategies={"Ubuntu_amd64": {"docker": {"installed_version_command": ["docker --version"]}}},
        installed_versions={192: {}},
        latest_versions_from_host={},
        application_states={},
        hosts_requiring_installation=[],
        requester_email="rashmi.sahu@ap2l.ai"
    )
    
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        
        mock_check.return_value = {
            "docker": {
                "installed_raw": "29.9.0",
                "package_version": "29.9.0",
                "binary_version": "29.9.0",
                "exit_code": 0
            }
        }
        
        check_updates = await check_application_state(state)
        state.update(check_updates)
        assert state["installed_versions"][192]["docker"] == "29.9.0"
        
        # Set version discovery attributes
        state["applications"][0]["version_resolution_source"] = "latest"
        state["applications"][0]["discovered_latest_version"] = "29.9.0"
        state["applications"][0]["version_availability_status"] = "AVAILABLE"
        state["applications"][0]["target_version"] = "29.9.0"
        
        decision_updates = version_decision(state)
        state.update(decision_updates)
        
        # Host should NOT require installation
        assert 192 not in state.get("hosts_requiring_installation", [])
        
        from app.graph.graph import store_application_result
        store_updates = store_application_result(state)
        state.update(store_updates)
        assert state["applications"][0]["installation_status"] in ["ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"]
        assert state["applications"][0]["status"] in ["ALREADY_INSTALLED", "NO_UPDATE_REQUIRED"]
        
        # Test notification delivery for ALREADY_INSTALLED
        with patch("app.database.database.SessionLocal"), \
             patch("app.services.email_service.EmailService.send_multi_app_report", return_value=(True, "Sent")) as mock_email:
            
            notif_state = dict(state)
            notif_result = await send_notification(notif_state)
            
            assert notif_result.get("status") == "SUCCESS"
            assert notif_result.get("email_sent") is True
            mock_email.assert_called_once()


# ==============================================================================
# WORKFLOW 5: Fresh Installation Pipeline Flow
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_5_fresh_installation_pipeline():
    """Test complete flow for an application not installed on the system."""
    app_dict = {"name": "jq", "version": "latest", "operation": "INSTALL"}
    state = InstallationState(
        job_id="job_fresh_install_test",
        application_name="jq",
        version="latest",
        applications=[app_dict],
        host_ids=[192],
        os_groups={"Ubuntu_amd64": [192]},
        strategies={"Ubuntu_amd64": {"jq": {"installed_version_command": ["jq --version"]}}},
        installed_versions={192: {}},
        latest_versions_from_host={},
        application_states={},
        hosts_requiring_installation=[],
        requester_email="rashmi.sahu@ap2l.ai"
    )
    
    # 1. State check detects not installed
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        
        mock_check.return_value = {
            "jq": {
                "installed_raw": None,
                "package_version": None,
                "binary_version": None,
                "exit_code": 0
            }
        }
        
        check_updates = await check_application_state(state)
        state.update(check_updates)
        assert 192 in state["hosts_requiring_installation"]
        
        # 2. Version discovery & decision confirms install required
        state["applications"][0]["version_resolution_source"] = "latest"
        state["applications"][0]["discovered_latest_version"] = "1.7.1"
        state["applications"][0]["version_availability_status"] = "AVAILABLE"
        state["applications"][0]["target_version"] = "1.7.1"
        
        decision_updates = version_decision(state)
        state.update(decision_updates)
        
        assert 192 in state["hosts_requiring_installation"]
        assert state["target_version"] == "1.7.1"
            
        # 3. Monitoring execution
        monitor_state = dict(state)
        monitor_state["execution_ids"] = ["exec-jq-192"]
        monitor_state["applications"][0]["state"] = "INSTALL_REQUIRED"
        
        with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
            mock_res.return_value = {
                "exit_code": 0,
                "host_timeout": False,
                "output": "DEPLOYIQ_RESULT_START\nAPPLICATION=jq\nINSTALLATION_STATUS=SUCCESS\nVERIFICATION_STATUS=SUCCESS\nINSTALLED_VERSION=1.7.1\nDEPLOYIQ_RESULT_END"
            }
            monitor_result = await monitor_execution(monitor_state)
            assert monitor_result.get("status") == "SUCCESS"
            assert monitor_result["applications"][0]["installation_status"] == "SUCCESS"


# ==============================================================================
# WORKFLOW 6: Application Update (Successful Upgrade)
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_6_application_update_upgrade():
    """Test update flow when installed version is older than target version."""
    app_dict = {"name": "brave-browser", "version": "latest", "operation": "UPDATE"}
    state = InstallationState(
        job_id="job_update_upgrade_test",
        application_name="brave-browser",
        version="latest",
        applications=[app_dict],
        host_ids=[192],
        os_groups={"Ubuntu_amd64": [192]},
        strategies={"Ubuntu_amd64": {"brave-browser": {"installed_version_command": ["brave-browser --version"]}}},
        installed_versions={192: {}},
        latest_versions_from_host={},
        application_states={},
        hosts_requiring_installation=[],
        requester_email="rashmi.sahu@ap2l.ai"
    )
    
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        
        mock_check.return_value = {
            "brave-browser": {
                "installed_raw": "1.90.0",
                "package_version": "1.90.0",
                "exit_code": 0
            }
        }
        
        check_updates = await check_application_state(state)
        state.update(check_updates)
        assert state["installed_versions"][192]["brave-browser"] == "1.90.0"
        
        # Version discovery discovers 1.95.0 > 1.90.0
        state["applications"][0]["version_resolution_source"] = "latest"
        state["applications"][0]["discovered_latest_version"] = "1.95.0"
        state["applications"][0]["version_availability_status"] = "AVAILABLE"
        state["applications"][0]["target_version"] = "1.95.0"
        
        decision_updates = version_decision(state)
        state.update(decision_updates)
        
        assert 192 in state["hosts_requiring_installation"]
        assert state["applications"][0]["operation"] == "UPDATE"
        assert state["target_version"] == "1.95.0"


# ==============================================================================
# WORKFLOW 7: Update Fallback to Fresh Install
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_7_update_fallback_to_fresh_install():
    """Test requesting UPDATE for an uninstalled software automatically falls back to INSTALL."""
    state = InstallationState(
        job_id="job_fallback_test",
        application_name="uninstalled-tool",
        version="latest",
        applications=[{"name": "uninstalled-tool", "version": "latest", "operation": "UPDATE"}],
        host_ids=[192],
        os_groups={"Ubuntu_amd64": [192]},
        strategies={"Ubuntu_amd64": {"uninstalled-tool": {"installed_version_command": ["false"]}}},
        installed_versions={192: {}},
        latest_versions_from_host={},
        application_states={},
        hosts_requiring_installation=[],
        requester_email="rashmi.sahu@ap2l.ai"
    )
    
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        
        mock_check.return_value = {
            "uninstalled-tool": {
                "installed_raw": None,
                "package_version": None,
                "binary_version": None,
                "exit_code": 0
            }
        }
        
        res = await check_application_state(state)
        app = res["applications"][0]
        
        # Verifies fallback triggered
        assert app.get("update_fallback_to_install") is True
        assert app.get("operation") == "INSTALL"
        assert 192 in res["hosts_requiring_installation"]


# ==============================================================================
# WORKFLOW 8: Version Downgrade Guardrail
# ==============================================================================
@pytest.mark.asyncio
async def test_workflow_8_version_downgrade_guardrail():
    """Test requesting an older version than installed triggers downgrade protection."""
    app_dict = {"name": "postgres", "version": "14.0", "operation": "INSTALL", "requested_version": "14.0"}
    state = InstallationState(
        job_id="job_downgrade_test",
        application_name="postgres",
        version="14.0",
        applications=[app_dict],
        host_ids=[192],
        os_groups={"Ubuntu_amd64": [192]},
        strategies={"Ubuntu_amd64": {"postgres": {"installed_version_command": ["postgres --version"]}}},
        installed_versions={192: {}},
        latest_versions_from_host={},
        application_states={},
        hosts_requiring_installation=[],
        requester_email="rashmi.sahu@ap2l.ai"
    )
    
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        
        # Already installed version 16.0, requested 14.0
        mock_check.return_value = {
            "postgres": {
                "installed_raw": "16.0",
                "package_version": "16.0",
                "exit_code": 0
            }
        }
        
        check_updates = await check_application_state(state)
        state.update(check_updates)
        assert state["installed_versions"][192]["postgres"] == "16.0"
        
        state["applications"][0]["version_resolution_source"] = "explicit"
        state["applications"][0]["requested_version"] = "14.0"
        state["applications"][0]["version_availability_status"] = "AVAILABLE"
        state["applications"][0]["target_version"] = "14.0"
        
        decision_updates = version_decision(state)
        state.update(decision_updates)
        
        # Installation must NOT be dispatched unconditionally
        assert 192 not in state.get("hosts_requiring_installation", [])
        assert state["applications"][0].get("status") in [
            "VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST",
            "AWAITING_USER_CLARIFICATION",
            "UPDATE_BLOCKED"
        ]
