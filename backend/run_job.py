import os
import uuid
import sys
# Add backend to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.queue_service import QueueService
from app.database.models import InstallationJob
from app.database.database import SessionLocal

def run():
    db = SessionLocal()
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    
    # Create the job in the database
    job = InstallationJob(
        id=job_id,
        application_id="3f91e22d-0208-4d2e-9e3a-0b87e347f194",
        host_id="1",
        status="PENDING"
    )
    db.add(job)
    db.commit()
    
    applications = [
        {"name": "jmeter", "version": "latest"},
        {"name": "nodejs", "version": "latest"},
        {"name": "remmina", "version": "latest"},
        {"name": "adb", "version": "latest"},
        {"name": "appium", "version": "latest"}
    ]
    
    # Enqueue
    task_id = QueueService.enqueue_installation(
        job_id=job_id,
        host_ids=[1],
        applications=applications,
        requester_email="rashmi.sahu@ap2l.ai"
    )
    print(f"Queued job {job_id} with task {task_id}")

if __name__ == "__main__":
    run()
