from app.graph.state import InstallationState
from app.services.application_strategy_service import ApplicationStrategyService
from app.services.llm_service import LLMService
from app.graph.nodes.utils import broadcast_stage, broadcast_log
from pydantic import BaseModel, Field
from typing import List, Optional
import json

class ApplicationStrategyResponse(BaseModel):
    package_manager: Optional[str] = Field(description="The package manager to use, if any (e.g., apt, brew, winget).")
    package_name: Optional[str] = Field(description="The exact package name to use for installation.")
    installation_method: str = Field(description="A brief description of how to install this application.")
    installed_version_command: List[str] = Field(description="The command (as an array of strings) to check the currently installed version (e.g. ['code', '--version']). Return empty list if not possible.")
    latest_version_command: List[str] = Field(description="The command (as an array of strings) to check the latest available version remotely (e.g. ['apt-cache', 'policy', 'code']). Return empty list if not possible.")
    latest_version_source: Optional[str] = Field(description="The source of the latest version check (e.g. 'apt', 'winget', 'github_api').")
    verification_command: List[str] = Field(description="The command (as an array of strings) to verify the application was successfully installed and executes properly.")

def application_strategy_discovery(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ApplicationStrategyDiscoveryAgent"
    stage_name = "APPLICATION_STRATEGY_DISCOVERY"
    
    if state.get("is_cancelled"):
        return {"status": "CANCELLED"}
        
    app_name = state.get("application_name")
    os_groups = state.get("os_groups", {})
    strategies = state.get("strategies", {})
    strategy_reused = state.get("strategy_reused", {})
    
    # Check if we actually need to run discovery
    if all(strategy_reused.get(sig, False) for sig in os_groups):
        return {} # All strategies already cached
        
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, f"Discovering installation strategies for {app_name} using AI")
    
    updates = {
        "strategies": strategies
    }
    
    for sig in os_groups:
        if strategy_reused.get(sig, False):
            continue
            
        parts = sig.split("_")
        os_name = parts[0]
        arch = parts[-1]
        os_version = parts[1] if len(parts) > 2 else ""
        
        broadcast_log(job_id, agent_name, f"Requesting AI strategy for {app_name} on {sig}")
        
        prompt = f"""
You are an expert system administrator agent. 
Determine the best way to install, verify, and check the version of the following application:
Application: {app_name}
Operating System: {os_name} {os_version}
Architecture: {arch}

You MUST return a JSON object that perfectly matches the following schema. Do NOT include any markdown, explanations, or prose outside the JSON.
Schema:
{{
    "package_manager": "string or null",
    "package_name": "string or null",
    "installation_method": "string",
    "installed_version_command": ["string"],
    "latest_version_command": ["string"],
    "latest_version_source": "string or null",
    "verification_command": ["string"]
}}

Rules:
1. installed_version_command must output the version string. It should be safe to run (e.g. use --user-data-dir /tmp for Chrome/VSCode to prevent root errors).
2. latest_version_command should check the remote repository (e.g. apt-cache policy, brew info --json=v2, winget show). If unavailable, return an empty array [].
3. For Windows, use completely non-interactive package-manager commands. If using winget, explicitly include --silent --accept-package-agreements --accept-source-agreements. Never require user input or open an interactive GUI.
"""

        try:
            # LLMService.generate generally expects the prompt directly. We parse JSON from it.
            response_text = LLMService.generate(prompt, json_mode=True)
            
            # Basic cleanup if wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].strip()
                
            data = json.loads(response_text)
            strategy = ApplicationStrategyResponse(**data)
            
            # Save to DB cache
            saved = ApplicationStrategyService.save_strategy(
                application_name=app_name,
                operating_system=os_name,
                os_version=os_version,
                architecture=arch,
                package_manager=strategy.package_manager,
                package_name=strategy.package_name,
                installation_method=strategy.installation_method,
                installed_version_command=strategy.installed_version_command,
                latest_version_command=strategy.latest_version_command,
                latest_version_source=strategy.latest_version_source,
                verification_command=strategy.verification_command
            )
            
            updates["strategies"][sig] = {
                "package_manager": strategy.package_manager,
                "package_name": strategy.package_name,
                "installation_method": strategy.installation_method,
                "installed_version_command": strategy.installed_version_command,
                "latest_version_command": strategy.latest_version_command,
                "latest_version_source": strategy.latest_version_source,
                "verification_command": strategy.verification_command
            }
            
            broadcast_log(job_id, agent_name, f"AI discovered and validated installation strategy for {sig}")
            
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Failed to discover strategy for {sig}: {e}", "error")
            return {"status": "FAILED"}
            
    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates
