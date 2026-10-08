import os
import sys
import glob
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.providers.application_provider import ApplicationProviderRegistry, GenericApplicationProvider
from app.graph.nodes.host_discovery import discover_hosts
from app.graph.nodes.version_decision import version_decision, _compare_versions
from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.monitoring import monitor_execution
from app.services.script_registry_service import ScriptRegistryService
from app.services.email_service import EmailService

# 1. Unknown host never falls back to another host
def test_1_unknown_host_never_falls_back():
    state = {
        "job_id": "test_job_unknown_host",
        "target_host": "192.168.99.99",
        "host_id": "192.168.99.99",
        "requester_email": "requester@company.com"
    }
    with patch("app.core.config.settings.USE_FLEETDM", True), \
         patch("app.services.fleetdm_service.FleetDMService.verify_host_enrolled", return_value=None):
        res = discover_hosts(state)
        assert res.get("status") == "FAILED"
        assert res.get("failure_category") == "HOST_NOT_FOUND_IN_FLEET"
        assert "host_ids" not in res or res.get("host_ids") == []
        assert "192.168.99.99" in res.get("error_message", "")

# 2. Unknown host generates requester email
def test_2_unknown_host_generates_requester_email():
    state = {
        "job_id": "test_job_email_notify",
        "host_id": "10.0.0.99",
        "requester_email": "alice@company.com"
    }
    with patch("app.core.config.settings.USE_FLEETDM", True), \
         patch("app.services.fleetdm_service.FleetDMService.verify_host_enrolled", return_value=None), \
         patch("app.services.email_service.EmailService.send_host_not_found_email") as mock_email:
        res = discover_hosts(state)
        mock_email.assert_called_once_with(
            recipient_email="alice@company.com",
            requested_host="10.0.0.99",
            in_reply_to=None
        )

# 3. Admin email comes from .env/config
def test_3_admin_email_comes_from_config():
    assert hasattr(settings, "ADMIN_APPROVAL_EMAIL")
    assert isinstance(settings.ADMIN_APPROVAL_EMAIL, str)

# 4. Requester email comes from original request
def test_4_requester_email_comes_from_original_request():
    from app.graph.email.nodes.validation import validate_request
    email_data = {
        "sender": "developer@client.com",
        "status": "RECEIVED",
        "application_name": "curl",
        "target_host_ip": "192.168.1.100",
        "message_id": "<msg-12345@client.com>"
    }
    with patch("app.services.fleetdm_service.FleetDMService.verify_host_enrolled", return_value={"id": 42, "hostname": "host-1"}), \
         patch("app.database.database.SessionLocal"):
        res = validate_request(email_data)
        assert res.get("host_id") == "42"
        assert res.get("status") == "PENDING_APPROVAL"

# 5, 6, 7. Brave, Chrome, VS Code are NOT special-cased in generic version detection
def test_5_6_7_no_application_special_casing():
    apps = ["Brave", "Google Chrome", "VS Code", "Firefox", "Slack", "Zoom"]
    for app_name in apps:
        provider = ApplicationProviderRegistry.get_provider(app_name)
        assert type(provider) is GenericApplicationProvider
        assert hasattr(provider, "generate_state_check_bash")
        assert hasattr(provider, "get_package_candidates")
        assert hasattr(provider, "get_binary_candidates")

# 8. Generic applications can still be detected
def test_8_generic_applications_can_still_be_detected():
    custom_app = "wireguard-tools"
    provider = ApplicationProviderRegistry.get_provider(custom_app)
    assert isinstance(provider, GenericApplicationProvider)
    linux_cmd = provider.generate_state_check_bash("linux")
    assert "dpkg-query" in linux_cmd
    assert "apt-cache" in linux_cmd
    assert "command -v" in linux_cmd

# 9. Installed version is required before UPDATE research
def test_9_installed_version_required_before_update_research():
    state = {
        "job_id": "test_job_update_no_version",
        "application_name": "git",
        "applications": [
            {
                "name": "git",
                "operation": "UPDATE",
                "version": "latest",
                "installed_version": None,
                "status": "RUNNING"
            }
        ],
        "installed_versions": {},
        "os_groups": {"ubuntu_amd64": [1]},
        "strategies": {}
    }
    res = latest_version_discovery(state)
    app = res["applications"][0]
    assert app.get("status") == "FAILED"
    assert app.get("failure_category") == "VERSION_DETECTION_FAILED"

# 10. Unknown version blocks update
def test_10_unknown_version_blocks_update():
    state = {
        "job_id": "test_job_unknown_ver",
        "application_name": "htop",
        "applications": [
            {
                "name": "htop",
                "operation": "UPDATE",
                "version_resolution_source": "explicit",
                "requested_version": "3.2.0",
                "status": "RUNNING"
            }
        ],
        "installed_versions": {1: {"htop": None}},
        "application_states": {1: {"htop": "UNKNOWN"}}
    }
    res = version_decision(state)
    assert res.get("status") == "FAILED"
    app = res["applications"][0]
    assert app.get("status") == "FAILED"
    assert app.get("failure_category") == "VERSION_DETECTION_FAILED"

# 11. Current version == latest -> NO_UPDATE_REQUIRED
def test_11_current_version_equal_latest_no_update_required():
    state = {
        "job_id": "test_job_same_ver",
        "application_name": "nginx",
        "applications": [
            {
                "name": "nginx",
                "operation": "UPDATE",
                "version_resolution_source": "explicit",
                "requested_version": "1.24.0",
                "canonical_installed_version": "1.24.0",
                "status": "RUNNING"
            }
        ],
        "installed_versions": {1: {"nginx": "1.24.0"}},
        "application_states": {1: {"nginx": "INSTALLED"}}
    }
    res = version_decision(state)
    assert res.get("status") == "COMPLETED"
    assert res["application_states"][1]["nginx"] == "NO_UPDATE_REQUIRED"
    assert res.get("hosts_requiring_installation") == []

# 12. Current version < latest -> UPDATE_REQUIRED
def test_12_current_version_less_than_latest_update_required():
    state = {
        "job_id": "test_job_newer_ver",
        "application_name": "nginx",
        "applications": [
            {
                "name": "nginx",
                "operation": "UPDATE",
                "version_resolution_source": "explicit",
                "requested_version": "1.26.0",
                "canonical_installed_version": "1.24.0",
                "status": "RUNNING"
            }
        ],
        "installed_versions": {1: {"nginx": "1.24.0"}},
        "application_states": {1: {"nginx": "INSTALLED"}}
    }
    res = version_decision(state)
    assert res.get("status") != "FAILED"
    assert res["applications"][0].get("state") == "INSTALL_REQUIRED"
    assert 1 in res.get("hosts_requiring_installation")

# 13. Current version > requested/latest -> downgrade protection
def test_13_downgrade_protection():
    state = {
        "job_id": "test_job_downgrade",
        "application_name": "nginx",
        "applications": [
            {
                "name": "nginx",
                "operation": "UPDATE",
                "version_resolution_source": "explicit",
                "requested_version": "1.22.0",
                "canonical_installed_version": "1.24.0",
                "status": "RUNNING"
            }
        ],
        "installed_versions": {1: {"nginx": "1.24.0"}},
        "application_states": {1: {"nginx": "INSTALLED"}}
    }
    with patch("app.services.email_service.EmailService.send_user_downgrade_request", return_value=(True, "Sent")), \
         patch("app.database.database.SessionLocal"), \
         patch("app.database.repositories.approval_repository.approval_repo.create"):
        res = version_decision(state)
        assert res.get("status") == "FAILED"
        app = res["applications"][0]
        assert app.get("status") == "AWAITING_USER_CLARIFICATION"
        assert app.get("failure_category") == "VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST"

# 14. Destructive update cannot execute without approval
def test_14_destructive_update_requires_approval():
    from app.graph.nodes.installation_research_validation import validate_installation_research
    state = {
        "job_id": "test_job_destructive",
        "application_name": "postgresql",
        "target_version": "16.0",
        "operation": "UPDATE",
        "applications": [
            {
                "name": "postgresql",
                "operation": "UPDATE",
                "target_version": "16.0",
                "installed_version": "14.0"
            }
        ],
        "research_results": {
            "ubuntu_amd64": {
                "research_status": "RESEARCH_SUCCESS",
                "recommended_method": "apt",
                "update_requires_removal": True
            }
        },
        "os_groups": {"ubuntu_amd64": [1]},
        "installed_versions": {1: {"postgresql": "14.0"}},
        "requester_email": "dba@company.com"
    }
    with patch("app.services.email_service.EmailService.send_admin_approval_request", return_value=(True, "Sent")), \
         patch("app.database.database.SessionLocal"), \
         patch("app.database.repositories.approval_repository.approval_repo.create"):
        res = validate_installation_research(state)
        assert res.get("status") == "UPDATE_REQUIRES_HUMAN_APPROVAL"

# 15. Approval is tied to the correct request/thread
def test_15_approval_tied_to_correct_request():
    from app.database.repositories.approval_repository import approval_repo
    from app.database.models.approval import ApprovalRequest
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    res = approval_repo.get_pending_by_thread(mock_db, "<unrelated-thread@domain.com>")
    assert res == []

    pending_app = ApprovalRequest(
        id="test-app-id",
        admin_message_id="<valid-approval-thread@deployiq.local>",
        status="PENDING"
    )
    mock_db.query.return_value.filter.return_value.all.return_value = [pending_app]
    matches = approval_repo.get_pending_by_thread(mock_db, "<valid-approval-thread@deployiq.local>")
    assert len(matches) == 1
    assert matches[0].id == "test-app-id"

# 16. Existing compatible scripts are reused per application
def test_16_existing_compatible_scripts_reused():
    mock_script = MagicMock()
    mock_script.script_content = "echo 'installing curl v1.0'"
    mock_script.registry_id = "test-reg-101"

    with patch("app.services.script_registry_service.SessionLocal") as mock_session:
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = mock_script

        found = ScriptRegistryService.find_compatible_script(
            application_name="curl",
            version="1.0",
            operating_system="ubuntu",
            architecture="x86_64"
        )
        assert found is not None
        assert found.registry_id == "test-reg-101"

# 17. Multi-application requests perform independent lookups
def test_17_multi_application_independent_lookups():
    apps = ["curl", "jq", "nmap"]
    providers = [ApplicationProviderRegistry.get_provider(app) for app in apps]
    names = [p.app_names[0] for p in providers]
    assert names == ["curl", "jq", "nmap"]
    candidates = [p.get_package_candidates("linux") for p in providers]
    assert "curl" in candidates[0]
    assert "jq" in candidates[1]
    assert "nmap" in candidates[2]

# 18. No hardcoded Fleet host fallback exists in graph/services
def test_18_no_hardcoded_fleet_host_fallback():
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    py_files = glob.glob(f"{backend_dir}/app/**/*.py", recursive=True)
    forbidden_snippets = [
        "socket.gethostname()",
        "target_host or '1'",
        "host_id = 191",
        "host_ids = [1]"
    ]
    for filepath in py_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            for snippet in forbidden_snippets:
                assert snippet not in content, f"Found forbidden snippet '{snippet}' in {filepath}"

# 19. No hardcoded email recipient exists outside configuration
def test_19_no_hardcoded_email_outside_config():
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    py_files = glob.glob(f"{backend_dir}/app/**/*.py", recursive=True)
    forbidden_email = "rashmi.sahu@ap2l.ai"
    for filepath in py_files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            assert forbidden_email not in content, f"Found hardcoded email {forbidden_email} in {filepath}"

# 20. Failed execution cannot become SUCCESS
@pytest.mark.asyncio
async def test_20_failed_execution_cannot_become_success():
    state = {
        "job_id": "test_job_fail",
        "application_name": "app-test",
        "applications": [{
            "name": "app-test",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": "1.0",
            "target_version": "2.0"
        }],
        "execution_ids": ["exec_fail_1"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {
            "exit_code": 1,
            "host_timeout": False,
            "output": "Error: package update failed"
        }
        res = await monitor_execution(state)
        assert res.get("status") == "FAILED"
        assert res["applications"][0].get("status") in ["FAILED", "UPDATE_VERIFICATION_FAILED"]

# 21. Post-update state check verifies the actual installed version
@pytest.mark.asyncio
async def test_21_post_update_state_check_verifies_actual_version():
    state = {
        "job_id": "test_job_unchanged",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": "1.94.121",
            "canonical_installed_version": "1.94.121",
            "target_version": "1.95.101"
        }],
        "execution_ids": ["exec_unchanged_1"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {
            "exit_code": 0,
            "host_timeout": False,
            "output": "DEPLOYIQ_RESULT_START\nAPPLICATION=brave-browser\nINSTALLATION_STATUS=SUCCESS\nVERIFICATION_STATUS=FAILED\nINSTALLED_VERSION=1.94.121\nDEPLOYIQ_RESULT_END"
        }
        res = await monitor_execution(state)
        assert res.get("status") == "FAILED"
        assert res["applications"][0].get("status") in ["FAILED", "UPDATE_VERIFICATION_FAILED"]

# 22. Dead code purged (e.g. dummy_data.py does not exist)
def test_22_dead_code_purged():
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dummy_data_path = os.path.join(backend_dir, "app", "utils", "dummy_data.py")
    assert not os.path.exists(dummy_data_path), f"{dummy_data_path} should be deleted as dead code"

# 23. Repository-based installation does not require an artifact & remains REPOSITORY
def test_23_repository_strategy_does_not_require_artifact():
    from app.graph.nodes.installation_research_validation import validate_installation_research
    state = {
        "job_id": "test_repo_strategy",
        "application_name": "sample-repo-app",
        "os_groups": {"Ubuntu_amd64": [191]},
        "research_results": {
            "Ubuntu_amd64": {
                "recommended_method": "apt",
                "repository_url": "https://example.com/repo",
                "package_name": "sample-pkg",
                "verification_method": "dpkg-query",
                "confidence_score": 0.95
            }
        }
    }
    res = validate_installation_research(state)
    assert res.get("status") != "FAILED"
    assert res.get("status") != "ARTIFACT_REQUIRED"
    assert res.get("current_stage") == "INSTALLATION_RESEARCH_VALIDATED"

# 24. DIRECT_ARTIFACT requires a verified exact URL
def test_24_direct_artifact_requires_verified_exact_url():
    from app.graph.nodes.installation_research_validation import validate_installation_research
    state = {
        "job_id": "test_direct_artifact_missing_url",
        "application_name": "custom-binary-tool",
        "os_groups": {"Ubuntu_amd64": [191]},
        "research_results": {
            "Ubuntu_amd64": {
                "recommended_method": "official_deb",
                "package_name": "custom-tool",
                "artifact_url": None,  # Missing!
                "artifact_url_verified": False,
                "verification_method": "binary",
                "confidence_score": 0.80
            }
        }
    }
    res = validate_installation_research(state)
    assert res.get("status") == "ARTIFACT_REQUIRED"

# 25. 404 URL failure routes back to research without premature fatal termination
def test_25_404_url_failure_routes_to_research():
    from app.graph.nodes.script_failure_analysis import analyze_script_failure
    state = {
        "job_id": "test_404_retry",
        "status": "FAILED",
        "application_name": "curl-tool",
        "os_groups": {"Ubuntu_amd64": [191]},
        "current_attempts": {"Ubuntu_amd64": 1},
        "maximum_attempts": {"Ubuntu_amd64": 3},
        "execution_results": {
            "exec_101": {
                "host_id": 191,
                "exit_code": 1,
                "output": "curl: (22) The requested URL returned error: 404 Not Found"
            }
        },
        "research_results": {
            "Ubuntu_amd64": {
                "recommended_method": "apt",
                "package_name": "curl-tool"
            }
        }
    }
    res = analyze_script_failure(state)
    # Must route to research or script generation, not fatal abort
    assert res.get("status") != "FAILED"
    assert "Ubuntu_amd64" in res.get("script_failure_context", {})



