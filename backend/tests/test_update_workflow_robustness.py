import pytest
from unittest.mock import patch, AsyncMock
from app.utils.version_utils import (
    canonicalize_version,
    compare_canonical_versions,
    is_newer_version,
    clean_version_string,
    parse_version_tuple
)
from app.graph.nodes.version_decision import version_decision
from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.monitoring import monitor_execution
import asyncio

# TEST A: Brave installed and version detected
def test_a_brave_installed_version_detected():
    binary_ver = "152.1.94.121"
    package_ver = "1.94.121"
    canonical, source = canonicalize_version(binary_ver, package_ver, "APT")
    assert canonical == "1.94.121"
    assert source == "APT"

# TEST B: Brave installed but binary unavailable through PATH (detected via dpkg-query or absolute path)
def test_b_brave_installed_binary_unavailable_in_path():
    binary_ver = None
    package_ver = "1.94.121"
    canonical, source = canonicalize_version(binary_ver, package_ver, "APT")
    assert canonical == "1.94.121"
    assert source == "APT"

# TEST C: Brave not installed
def test_c_brave_not_installed():
    state = {
        "job_id": "test_job_c",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "version": "latest"
        }],
        "os_groups": {"ubuntu_x86_64": [191]},
        "strategies": {"ubuntu_x86_64": {"brave-browser": {"installed_version_command": ["false"]}}},
        "installed_versions": {191: {"brave-browser": None}},
        "latest_versions_from_host": {},
        "application_states": {}
    }
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="123"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        mock_check.return_value = {"brave-browser": {"installed_raw": None, "latest_raw": None, "exit_code": 0}}
        res = asyncio.run(check_application_state(state))
        app = res["applications"][0]
        assert app.get("update_fallback_to_install") is True
        assert app.get("operation") == "INSTALL"
        assert 191 in res["hosts_requiring_installation"]

# TEST D: State detection command fails
def test_d_state_detection_command_fails():
    state = {
        "job_id": "test_job_d",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "version": "latest"
        }],
        "os_groups": {"ubuntu_x86_64": [191]},
        "strategies": {"ubuntu_x86_64": {"brave-browser": {"installed_version_command": ["false"]}}},
        "installed_versions": {191: {"brave-browser": None}},
        "latest_versions_from_host": {},
        "application_states": {}
    }
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="123"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        mock_check.return_value = {"brave-browser": {"installed_raw": None, "latest_raw": None, "exit_code": 1, "error_message": "Command error"}}
        res = asyncio.run(check_application_state(state))
        app = res["applications"][0]
        assert app["failure_category"] in ("VERSION_DETECTION_FAILED", "STATE_CHECK_FAILED")

# TEST E: State detection returns empty output
def test_e_state_detection_returns_empty_output():
    state = {
        "job_id": "test_job_e",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "version": "latest"
        }],
        "os_groups": {"ubuntu_x86_64": [191]},
        "strategies": {"ubuntu_x86_64": {"brave-browser": {"installed_version_command": ["false"]}}},
        "installed_versions": {191: {"brave-browser": None}},
        "latest_versions_from_host": {},
        "application_states": {}
    }
    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="123"), \
         patch("app.graph.nodes.application_state_check._check_on_host", new_callable=AsyncMock) as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):
        mock_check.return_value = {}
        res = asyncio.run(check_application_state(state))
        app = res["applications"][0]
        assert app["status"] == "FAILED"
        assert app["failure_category"] == "STATE_CHECK_FAILED"

# TEST F: Tavily returns an older version
def test_f_tavily_returns_older_version():
    installed = "1.94.121"
    candidate = "1.85.118"
    assert is_newer_version(candidate, installed) is False
    assert compare_canonical_versions(candidate, installed) == -1

# TEST G: Tavily returns the same version
def test_g_tavily_returns_same_version():
    state = {
        "job_id": "test_job_g",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "version": "1.94.121",
            "requested_version": "1.94.121",
            "version_resolution_source": "explicit",
            "canonical_installed_version": "1.94.121"
        }],
        "installed_versions": {191: {"brave-browser": "1.94.121"}},
        "application_states": {191: {"brave-browser": "INSTALLED"}}
    }
    res = version_decision(state)
    assert res["application_states"][191]["brave-browser"] == "NO_UPDATE_REQUIRED"

# TEST H: Tavily returns a newer version
def test_h_tavily_returns_newer_version():
    installed = "1.94.121"
    candidate = "1.95.101"
    assert is_newer_version(candidate, installed) is True

# TEST I: Update succeeds and post-check confirms newer version
def test_i_update_succeeds_post_check_confirms_newer():
    state = {
        "job_id": "test_job_i",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": "1.95.101",
            "canonical_installed_version": "1.94.121",
            "target_version": "1.95.101"
        }],
        "execution_ids": ["exec_i"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {
            "exit_code": 0,
            "host_timeout": False,
            "output": "DEPLOYIQ_RESULT_START\nAPPLICATION=brave-browser\nINSTALLATION_STATUS=SUCCESS\nVERIFICATION_STATUS=SUCCESS\nINSTALLED_VERSION=1.95.101\nDEPLOYIQ_RESULT_END"
        }
        res = asyncio.run(monitor_execution(state))
        app = res["applications"][0]
        assert app["verification_status"] == "SUCCESS"
        assert app["status"] == "UPDATE_SUCCESS"

# TEST J: FleetDM execution succeeds but application version does not change
def test_j_fleetdm_succeeds_version_unchanged():
    state = {
        "job_id": "test_job_j",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": "1.94.121",
            "canonical_installed_version": "1.94.121",
            "target_version": "1.95.101"
        }],
        "execution_ids": ["exec_j"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {
            "exit_code": 0,
            "host_timeout": False,
            "output": "DEPLOYIQ_RESULT_START\nAPPLICATION=brave-browser\nINSTALLATION_STATUS=SUCCESS\nVERIFICATION_STATUS=FAILED\nINSTALLED_VERSION=1.94.121\nDEPLOYIQ_RESULT_END"
        }
        res = asyncio.run(monitor_execution(state))
        app = res["applications"][0]
        assert app["verification_status"] == "FAILED"
        assert app["status"] == "UPDATE_VERIFICATION_FAILED"

# TEST K: Post-update version detection fails
def test_k_post_update_version_detection_fails():
    state = {
        "job_id": "test_job_k",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": None,
            "target_version": "1.95.101"
        }],
        "execution_ids": ["exec_k"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {"exit_code": 0, "output": "Execution finished"}
        res = asyncio.run(monitor_execution(state))
        app = res["applications"][0]
        assert app["verification_status"] == "FAILED"
        assert app["status"] == "UPDATE_VERIFICATION_FAILED"

# TEST L: Destructive update requiring human approval
def test_l_destructive_update_requires_human_approval():
    state = {
        "job_id": "test_job_l",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "UPDATE",
            "version": "1.94.121",
            "requested_version": "1.94.121",
            "version_resolution_source": "explicit",
            "canonical_installed_version": "1.95.101"
        }],
        "installed_versions": {191: {"brave-browser": "1.95.101"}},
        "application_states": {191: {"brave-browser": "INSTALLED"}}
    }
    res = version_decision(state)
    app = res["applications"][0]
    assert app["status"] == "AWAITING_USER_CLARIFICATION"

# TEST M: Explicit downgrade request
def test_m_explicit_downgrade_request():
    state = {
        "job_id": "test_job_m",
        "application_name": "brave-browser",
        "applications": [{
            "name": "brave-browser",
            "operation": "DOWNGRADE",
            "version": "1.94.121",
            "requested_version": "1.94.121",
            "version_resolution_source": "explicit",
            "canonical_installed_version": "1.95.101"
        }],
        "installed_versions": {191: {"brave-browser": "1.95.101"}},
        "application_states": {191: {"brave-browser": "INSTALLED"}}
    }
    res = version_decision(state)
    app = res["applications"][0]
    assert app["state"] == "INSTALL_REQUIRED"
    assert res["application_states"][191]["brave-browser"] == "DOWNGRADE_REQUESTED"


# TEST N: Google Chrome update where script outputs APPLICATION=chrome and Debian version with suffix
def test_n_chrome_script_alias_matching_and_update_success():
    from app.utils.version_utils import app_matches
    assert app_matches("google chrome", "chrome") is True
    assert app_matches("chrome", "google chrome") is True
    assert app_matches("google-chrome", "chrome") is True
    assert app_matches("google_chrome", "chrome") is True
    assert app_matches("google-chrome-stable", "google chrome") is True
    assert app_matches("brave", "brave-browser") is True
    assert app_matches("vscode", "code") is True
    assert app_matches("google chrome", "firefox") is False

    state = {
        "job_id": "test_job_chrome_update",
        "application_name": "google chrome",
        "applications": [{
            "name": "google chrome",
            "operation": "UPDATE",
            "state": "INSTALL_REQUIRED",
            "installed_version": "152.0.7977.82",
            "canonical_installed_version": "152.0.7977.82",
            "target_version": "154.0.8037.92"
        }],
        "execution_ids": ["exec_chrome_1"],
        "hosts_requiring_installation": [191],
        "host_ids": [191]
    }
    with patch("app.services.fleetdm_service.FleetDMService.get_script_result") as mock_res:
        mock_res.return_value = {
            "exit_code": 0,
            "host_timeout": False,
            "output": (
                "Installing google-chrome-stable...\n"
                "Verifying installation...\n"
                "Note: Installed version 154.0.8037.97-1 differs from target 154.0.8037.41\n"
                "DEPLOYIQ_RESULT_START\n"
                "APPLICATION=chrome\n"
                "INSTALLATION_STATUS=SUCCESS\n"
                "VERIFICATION_STATUS=SUCCESS\n"
                "INSTALLED_VERSION=154.0.8037.97-1\n"
                "DEPLOYIQ_RESULT_END\n"
            )
        }
        res = asyncio.run(monitor_execution(state))
        app = res["applications"][0]
        assert app["installed_version"] == "154.0.8037.97"
        assert app["installation_status"] == "SUCCESS"
        assert app["verification_status"] == "SUCCESS"
        assert app["status"] == "UPDATE_SUCCESS"
        assert res["status"] == "SUCCESS"


# TEST O: VSCode update state-check where host returns {"code": {...}}
def test_o_vscode_alias_state_check_and_discovery():
    from app.graph.nodes.application_state_check import check_application_state
    from app.graph.nodes.latest_version_discovery import latest_version_discovery

    state = {
        "job_id": "test_job_vscode",
        "application_name": "vscode",
        "applications": [{
            "name": "vscode",
            "operation": "UPDATE",
            "version": "latest",
        }],
        "host_ids": [191],
        "host_operating_systems": {191: "Ubuntu_amd64"},
        "os_groups": {"Ubuntu_amd64": [191]},
        "strategies": {
            "Ubuntu_amd64": {
                "vscode": {
                    "installed_version_command": ["code", "--version"],
                    "package_manager": "APT"
                }
            }
        },
        "installed_versions": {},
        "latest_versions_from_host": {},
        "application_states": {}
    }

    with patch("app.graph.nodes.application_state_check._upload_state_check_script", return_value="999"), \
         patch("app.graph.nodes.application_state_check._check_on_host") as mock_check, \
         patch("app.services.fleetdm_service.FleetDMService.delete_script"):

        # Mock the host returning output keyed by "code"
        mock_check.return_value = {
            "code": {
                "installed_raw": "1.124.2",
                "latest_raw": "1.136.2",
                "package_version": "1.124.2",
                "binary_version": None,
                "method": "dpkg-query:code",
                "exit_code": 0,
                "app_present": True,
                "error_message": ""
            }
        }

        res_check = asyncio.run(check_application_state(state))
        app = res_check["applications"][0]
        assert app.get("status") != "FAILED"
        assert app["installed_version"] == "1.124.2"
        assert res_check["installed_versions"][191]["vscode"] == "1.124.2"
        assert res_check["latest_versions_from_host"][191]["vscode"] == "1.136.2"

        # Now test latest_version_discovery with this state
        state_for_discovery = {**state, **res_check}
        res_disc = latest_version_discovery(state_for_discovery)
        disc_app = res_disc["applications"][0]
        assert disc_app.get("status") != "FAILED"
        assert disc_app["target_version"] == "1.136.2"
        assert disc_app["discovered_latest_version"] == "1.136.2"


