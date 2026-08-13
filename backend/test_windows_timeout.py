import asyncio
import os
import sys

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.graph.state import InstallationState
from app.graph.graph import create_installation_graph
from app.core.logger import logger, current_job_id, setup_job_logger, remove_job_logger
from app.database.database import Base, engine

Base.metadata.create_all(bind=engine)

async def test_windows_timeout():
    job_id = "test_win_firefox"
    token = current_job_id.set(job_id)
    file_handler = setup_job_logger(job_id)
    logger.info("Test Windows Firefox Job Started")

    initial_state = {
        "job_id": job_id,
        "application_id": "firefox_test_id",
        "application_name": "Firefox",
        "version": "Latest",
        "minimum_battery_percentage": 30,
        "category": "Browser",
        "description": "Mozilla Firefox browser",
        "status": "RUNNING",
        "current_stage": "INITIALIZED",
        "host_ids": [18],
        "risk_reasons": [],
        "execution_ids": [],
        "verification_results": {}
    }

    graph = create_installation_graph()
    
    print("Testing Windows Firefox Install on Host 18...")
    final_state = await graph.ainvoke(initial_state)
    
    print("\n--- FINAL STATE ---")
    print(f"Status: {final_state.get('status')}")
    print(f"Current Stage: {final_state.get('current_stage')}")
    print(f"Error Message: {final_state.get('error_message')}")
    
    # Print out script content for verification
    for sig, content in final_state.get('script_contents', {}).items():
        print(f"\n--- Script Content for {sig} ---")
        print(content)
        
    remove_job_logger(file_handler)
    current_job_id.reset(token)

if __name__ == "__main__":
    asyncio.run(test_windows_timeout())
