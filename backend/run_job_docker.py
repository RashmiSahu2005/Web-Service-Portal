import os
import uuid
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.queue_service import QueueService
from app.database.models import InstallationJob
from app.database.database import SessionLocal

def run():
    db = SessionLocal()
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    
    job = InstallationJob(
        id=job_id,
        application_id="ef680b24-a385-49c7-8b3d-94667524778c",
        host_id="24",
        status="PENDING"
    )
    db.add(job)
    db.commit()
    
    applications = [
        {"name": "docker", "version": "latest"}
    ]
    
    task_id = QueueService.enqueue_installation(
        job_id=job_id,
        host_ids=[24],
        applications=applications,
        requester_email="rashmi.sahu@ap2l.ai"
    )
    print(f"Queued job {job_id} with task {task_id}")

if __name__ == "__main__":
    run()
