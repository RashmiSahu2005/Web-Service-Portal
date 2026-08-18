import asyncio
from celery import shared_task
from app.database.database import SessionLocal
from app.database.models.job import InstallationJob
from app.database.models.application import Application
from app.graph.graph import create_installation_graph
from app.graph.state import InstallationState
from app.core.logger import logger

@shared_task(name="app.tasks.installation_tasks.run_installation_job", bind=True)
def run_installation_job(self, job_id: str):
    logger.info(f"Celery worker processing installation job: {job_id}")
    
    db = SessionLocal()
    try:
        job = db.query(InstallationJob).filter(InstallationJob.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return
            
        if job.status not in ["QUEUED", "PENDING"]:
            logger.warning(f"Job {job_id} is in state '{job.status}', expected 'QUEUED'. Skipping.")
            return
            
        app = db.query(Application).filter(Application.id == job.application_id).first()
        if not app:
            logger.error(f"Application for job {job_id} not found.")
            job.status = "FAILED"
            db.commit()
            return
            
        # Initialize Graph and State
        graph = create_installation_graph()
        host_ids = [job.host_id] if job.host_id and job.host_id != "dynamic" else [1] # Fallback
        
        initial_state = InstallationState(
            job_id=job.id,
            application_name=app.name,
            version=app.version or "Latest",
            host_ids=host_ids,
            current_stage="PENDING",
            status="RUNNING"
        )
        
        # Update Job Status to RUNNING
        job.status = "RUNNING"
        db.commit()
        
        # Execute Workflow
        logger.info(f"Starting LangGraph workflow for job {job_id}")
        asyncio.run(graph.ainvoke(initial_state))
        logger.info(f"LangGraph workflow completed for job {job_id}")
        
    except Exception as e:
        logger.error(f"Error executing installation job {job_id}: {e}", exc_info=True)
        # Attempt to mark job as failed if possible
        try:
            job = db.query(InstallationJob).filter(InstallationJob.id == job_id).first()
            if job and job.status not in ["COMPLETED", "CANCELLED"]:
                job.status = "FAILED"
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()
