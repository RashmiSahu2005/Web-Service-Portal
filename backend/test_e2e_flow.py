import asyncio
from app.tasks.installation_tasks import run_installation_job
from app.database.database import SessionLocal
from app.database.models.job import InstallationJob
from app.database.models.application import Application
import uuid

def test_postman():
    db = SessionLocal()
    
    app = db.query(Application).filter(Application.name == "JMeter").first()
    if not app:
        app = Application(id=str(uuid.uuid4()), name="JMeter", version="latest", category="Testing")
        db.add(app)
        db.commit()
    
    # Create a dummy pending job
    job_id = str(uuid.uuid4())
    job = InstallationJob(
        id=job_id,
        application_id=app.id,
        host_id=191, # Use the user's host ID for 192.168.10.83
        status="QUEUED"
    )
    db.add(job)
    db.commit()
    db.close()
    
    print(f"Running test for job_id: {job_id}")
    
    # We pass the applications explicitly so we can test whatever we want
    applications = [
        {"name": "JMeter", "version": "latest", "state": "INSTALL_REQUIRED"}
    ]
    
    run_installation_job(job_id, requester_email="test@localhost", applications=applications)

if __name__ == "__main__":
    test_postman()
