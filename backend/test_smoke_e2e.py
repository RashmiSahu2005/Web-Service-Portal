import asyncio
import os
import uuid
from unittest.mock import patch

from app.graph.graph import create_installation_graph
from app.core.config import settings

def run_smoke_test():
    # Make sure we use real FleetDM
    settings.USE_FLEETDM = True
    settings.REAL_FLEET_TEST = True
    
    # Generate a job ID
    job_id = f"smoke_test_{uuid.uuid4().hex[:8]}"
    print(f"Starting E2E Smoke Test: {job_id}")
    
    initial_state = {
        "job_id": job_id,
        "application_id": "99",
        "application_name": "ApplicationHub Smoke Test App",
        "version": "1.0",
        "current_stage": "INITIALIZED",
        "status": "RUNNING",
        "host_ids": [],
        "risk_reasons": [],
        "execution_ids": [],
        "verification_results": {}
    }
    from datetime import datetime
    initial_state["started_at"] = datetime.utcnow()
    
    smoke_script = """#!/usr/bin/env python3
import sys
import os

print("Starting ApplicationHub Smoke Test...")
filepath = "/tmp/applicationhub_agent_test.txt"
with open(filepath, "w") as f:
    f.write("ApplicationHub Agentic Deployment Test\\n")
print(f"Successfully created {filepath}")
sys.exit(0)
"""
    
    # We will patch LLM generation to return our safe script to ensure it does exactly what's needed.
    # We will also patch RiskAnalysis to guarantee it passes.
    # We will patch VerificationAgent's check to run `cat /tmp/applicationhub_agent_test.txt` or similar, 
    # but VerificationAgent runs a command via FleetDM or SSH? 
    # Wait, VerificationAgent currently runs a predefined verification_command locally? 
    # Let's check verification_agent.py
    
    def mock_llm_generate(prompt: str):
        if "script" in prompt.lower() and "json" not in prompt.lower() and "risk" not in prompt.lower():
            return smoke_script
        else:
            return '{"risk_score": 10, "risk_level": "LOW", "reasons": ["Safe smoke test"]}'

    with patch("app.services.llm_service.LLMService.generate", side_effect=mock_llm_generate):
         
        graph = create_installation_graph()
        
        loop = asyncio.get_event_loop()
        result_ctx = loop.run_until_complete(graph.ainvoke(initial_state))
        
        print("="*60)
        print("TEST RESULT")
        print(f"Status: {result_ctx.get('status')}")
        print(f"Error: {result_ctx.get('error_message')}")
        print(f"Verification: {result_ctx.get('verification_result')}")
        print("="*60)
        
        if result_ctx.get("status") == "COMPLETED" and result_ctx.get("verification_result") is True:
            print("E2E Smoke Test PASSED!")
        else:
            print("E2E Smoke Test FAILED!")

if __name__ == "__main__":
    run_smoke_test()
