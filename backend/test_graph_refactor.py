import asyncio
import os
from app.graph.state import InstallationState
from app.graph.graph import create_installation_graph
from app.core.logger import logger, current_job_id, setup_job_logger, remove_job_logger
from app.database.database import Base, engine

# Ensure DB is created
Base.metadata.create_all(bind=engine)

async def test_graph():
    job_id = "test_job_1"
    token = current_job_id.set(job_id)
    file_handler = setup_job_logger(job_id)
    logger.info("Test Job Started")

    initial_state = {
        "job_id": job_id,
        "application_id": "test_app_id",
        "application_name": "Brave Browser",
        "version": "Latest",
        "operating_system": "Ubuntu",
        "architecture": "amd64",
        "minimum_battery_percentage": 30,
        "category": "Browser",
        "description": "Brave browser",
        "status": "RUNNING",
        "current_stage": "INITIALIZED",
        "host_ids": [191, 205],
        "risk_reasons": [],
        "execution_ids": [],
        "verification_results": {}
    }

    graph = create_installation_graph()
    
    print("Testing First Install (Miss)...")
    final_state_1 = await graph.ainvoke(initial_state)
    print("Final State 1 Status:", final_state_1.get("status"))
    print("Script Reused 1:", final_state_1.get("script_reused"))
    
    remove_job_logger(file_handler)
    current_job_id.reset(token)

    job_id = "test_job_2"
    token = current_job_id.set(job_id)
    file_handler = setup_job_logger(job_id)
    logger.info("Test Job 2 Started")

    print("\nTesting Second Install (Hit)...")
    initial_state["job_id"] = job_id
    final_state_2 = await graph.ainvoke(initial_state)
    print("Final State 2 Status:", final_state_2.get("status"))
    print("Script Reused 2:", final_state_2.get("script_reused"))
    
    remove_job_logger(file_handler)
    current_job_id.reset(token)

if __name__ == "__main__":
    asyncio.run(test_graph())
