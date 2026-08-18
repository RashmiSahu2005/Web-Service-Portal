import asyncio
from unittest.mock import patch, MagicMock
from app.graph.graph import create_installation_graph
from app.graph.state import InstallationState
from app.database.database import Base, engine

# Initialize tables for tests
Base.metadata.create_all(bind=engine)

@patch('app.core.config.settings.USE_FLEETDM', False)
@patch('app.services.llm_service.LLMService.generate')
@patch('app.graph.graph.discover_hosts')
async def test_multi_os_installation(mock_discover_hosts, mock_llm_generate):
    def mock_discovery(state):
        return {"current_stage": "HOSTS_DISCOVERED", "host_ids": [1, 2, 3, 4]}
    mock_discover_hosts.side_effect = mock_discovery
    """
    Test the entire workflow with different OS groups.
    Host 1 -> Ubuntu amd64
    Host 2 -> Ubuntu arm64
    Host 3 -> Windows x64
    Host 4 -> macOS arm64
    """
    def llm_side_effect(prompt, **kwargs):
        if "package_manager" in prompt:
            return '{"package_manager": "apt", "package_name": "brave", "installation_method": "apt install", "installed_version_command": ["brave", "--version"], "latest_version_command": ["apt", "policy"], "latest_version_source": "apt", "verification_command": ["brave", "--version"]}'
        
        if "Windows" in prompt:
            return "```python\n#!/usr/bin/env python3\nprint('Windows install')\n```"
        elif "macOS" in prompt:
            return "```python\n#!/usr/bin/env python3\nprint('macOS install')\n```"
        else:
            return "```python\n#!/usr/bin/env python3\nprint('Linux install')\n```"
            
    mock_llm_generate.side_effect = llm_side_effect
    
    graph = create_installation_graph()
    
    initial_state = InstallationState(
        job_id="test_os_job",
        application_name="Brave",
        version="Latest",
        host_ids=[1, 2, 3, 4],
        current_stage="PENDING",
        status="RUNNING"
    )
    
    final_state = await graph.ainvoke(initial_state)
    
    assert final_state["status"] == "COMPLETED"
    
    os_groups = final_state["os_groups"]
    assert "Ubuntu_amd64" in os_groups
    assert "Ubuntu_arm64" in os_groups
    assert "Windows_x64" in os_groups
    assert "macOS_arm64" in os_groups
    
    assert final_state.get("verification_result") is True
    print("Test passed successfully!")

if __name__ == "__main__":
    asyncio.run(test_multi_os_installation())
