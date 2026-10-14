import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.tasks.installation_tasks import run_installation_job
from app.database.database import SessionLocal
from app.database.models.job import InstallationJob

def run_sync():
    db = SessionLocal()
    # Get the latest pending job
    job = db.query(InstallationJob).filter(InstallationJob.status == "PENDING").first()
    
    if not job:
        print("No pending jobs found!")
        return
        
    print(f"Executing job {job.id} synchronously...")
    
    # We can just call the celery task synchronously.
    # We need the task_id. We'll just generate one or use the job id.
    try:
        run_installation_job(job.id)
        print("Job completed!")
    except Exception as e:
        print(f"Error running job: {e}")

if __name__ == "__main__":
    run_sync()
