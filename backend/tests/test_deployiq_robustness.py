import pytest
import os
import sys

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.graph.nodes.version_decision import _compare_versions, version_decision
from app.graph.nodes.latest_version_discovery import latest_version_discovery
from app.graph.nodes.application_state_check import check_application_state
from app.graph.nodes.notification import send_notification

def test_version_comparison_tuples():
    # TEST 1: Standard minor/patch updates
    assert _compare_versions("1.124.2", "1.139.1") == -1
    assert _compare_versions("1.136.2", "1.139.1") == -1

    # TEST 2: Equality
    assert _compare_versions("1.139.1", "1.139.1") == 0
    assert _compare_versions("v1.94.121", "1.94.121") == 0

    # TEST 3: Multi-component & high major version comparison (e.g. Brave 152.1.94.121 vs 1.85.118)
    assert _compare_versions("152.1.94.121", "1.85.118") == 1
    assert _compare_versions("1.85.118", "152.1.94.121") == -1

def test_explicit_target_version_preservation():
    state = {
        "job_id": "test_job_1",
        "application_name": "Brave",
        "applications": [
            {
                "name": "Brave",
                "version": "1.94.121",
                "operation": "INSTALL"
            }
        ],
        "strategies": {
            "ubuntu_amd64": {
                "Brave": {
                    "installation_method": "apt",
                    "package_manager": "apt"
                }
            }
        }
    }
    res = latest_version_discovery(state)
    app = res["applications"][0]
    assert app.get("requested_version") == "1.94.121"
    assert app.get("version_resolution_source") == "explicit"

def test_stale_web_version_rejection():
    state = {
        "job_id": "test_job_2",
        "application_name": "Brave",
        "applications": [
            {
                "name": "Brave",
                "version": "latest",
                "operation": "UPDATE"
            }
        ],
        "installed_versions": {1: {"Brave": "152.1.94.121"}},
        "latest_versions_from_host": {},
        "os_groups": {"ubuntu_amd64": [1]},
        "strategies": {}
    }
    # Latest version discovery should reject candidate if lower than installed 152.1.94.121
    res = latest_version_discovery(state)
    app = res["applications"][0]
    # Should not produce a target lower than 152.1.94.121
    disc = app.get("discovered_latest_version")
    if disc:
        assert _compare_versions("152.1.94.121", disc) <= 0

def test_downgrade_protection_node():
    state = {
        "job_id": "test_job_3",
        "application_name": "Brave",
        "applications": [
            {
                "name": "Brave",
                "requested_version": "1.85.118",
                "version_resolution_source": "explicit",
                "operation": "UPDATE",
                "status": "RUNNING"
            }
        ],
        "installed_versions": {1: {"Brave": "152.1.94.121"}},
        "application_states": {1: {"Brave": "INSTALLED"}}
    }
    res = version_decision(state)
    # The application status should be blocked/awaiting clarification, not success
    assert res.get("status") in ["FAILED", "BLOCKED"]
    app = res["applications"][0]
    assert app.get("status") == "AWAITING_USER_CLARIFICATION"

if __name__ == "__main__":
    pytest.main([__file__])
