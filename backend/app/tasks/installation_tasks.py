import asyncio
import time
from celery import shared_task
from app.database.database import SessionLocal
from app.database.models.job import InstallationJob
from app.database.models.application import Application
from app.graph.graph import create_installation_graph
from app.graph.state import InstallationState
from app.core.logger import logger
from app.services.agent_event_service import AgentEventService

@shared_task(name="app.tasks.installation_tasks.run_installation_job", bind=True)
def run_installation_job(self, job_id: str, **kwargs):
    requester_email = kwargs.get("requester_email")
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
        if job.host_id and job.host_id not in ("dynamic", "none", "null"):
            host_ids = [job.host_id]
        elif not settings.USE_FLEETDM:
            host_ids = [settings.MOCK_HOST_ID]
        else:
            host_ids = []
        
        applications = kwargs.get("applications")
        if not applications:
            # Fallback for single-app API requests that didn't pass applications
            applications = [{"name": app.name, "version": app.version or "Latest"}]
            
        initial_state = InstallationState(
            job_id=job.id,
            applications=applications,
            application_name=app.name,
            version=app.version or "Latest",
            application_id=str(job.application_id),
            host_ids=host_ids,
            current_stage="PENDING",
            status="RUNNING",
            requester_email=requester_email,
            current_app_index=0
        )
        
        # Update Job Status to RUNNING
        job.status = "RUNNING"
        db.commit()
        
        # Execute Workflow
        logger.info(f"Starting LangGraph workflow for job {job_id}")
        start_time = time.time()
        config = {"recursion_limit": 300}
        asyncio.run(graph.ainvoke(initial_state, config))
        elapsed_time = time.time() - start_time
        logger.info(f"LangGraph workflow completed for job {job_id}. Overall time taken: {elapsed_time:.2f} seconds.")

        job = db.query(InstallationJob).filter(InstallationJob.id == job_id).first()
        if job and job.status not in ["CANCELLED"]:
            from datetime import datetime
            job.status = "COMPLETED"
            job.completed_at = datetime.utcnow()
            db.commit()
        
    except Exception as e:
        logger.error(f"Error executing installation job {job_id}: {e}", exc_info=True)
        # Attempt to mark job as failed if possible
        try:
            job = db.query(InstallationJob).filter(InstallationJob.id == job_id).first()
            if job and job.status not in ["COMPLETED", "CANCELLED"]:
                job.status = "FAILED"
                db.commit()
            
            # Broadcast to frontend so UI stops spinning
            AgentEventService.broadcast_overall_status(
                job_id=job_id,
                status="FAILED",
                error_message=f"Internal workflow error: {str(e)}"
            )
        except Exception as db_e:
            logger.error(f"Failed to update job status in DB: {db_e}")
            
        # Return cleanly so the Celery worker process is not killed
        return
    finally:
        db.close()

@shared_task(name="app.tasks.installation_tasks.resume_approved_update", bind=True)
def resume_approved_update(self, approval_request_id: str):
    from app.database.repositories.approval_repository import approval_repo
    from app.graph.resume_graph import create_resume_update_graph
    
    logger.info(f"Resuming approved update: {approval_request_id}")
    db = SessionLocal()
    try:
        req = approval_repo.get(db, approval_request_id)
        if not req:
            logger.error(f"ApprovalRequest {approval_request_id} not found.")
            return
            
        req.status = "EXECUTING"
        db.commit()

        graph = create_resume_update_graph()
        
        initial_state = InstallationState(
            job_id=req.job_id,
            applications=[{"name": req.application, "version": req.target_version, "status": "PENDING"}],
            application_name=req.application,
            target_version=req.target_version,
            host_ids=[int(req.host_id)],
            os_groups={req.os_signature: [int(req.host_id)]},
            research_results={req.os_signature: req.update_strategy},
            current_stage="PENDING",
            status="RUNNING",
            requester_email=req.original_requester_email,
            current_app_index=0,
            operation="DOWNGRADE" if req.approval_reason == "DOWNGRADE_REQUEST" else "UPDATE",
            is_resume_update=True,
            approval_request_id=approval_request_id
        )

        logger.info(f"Starting resume update workflow for approval {approval_request_id}")
        start_time = time.time()
        config = {"recursion_limit": 300}
        asyncio.run(graph.ainvoke(initial_state, config))
        elapsed_time = time.time() - start_time
        logger.info(f"Resume workflow completed in {elapsed_time:.2f} seconds.")
        
    except Exception as e:
        logger.error(f"Error resuming update {approval_request_id}: {e}", exc_info=True)
    finally:
        db.close()

