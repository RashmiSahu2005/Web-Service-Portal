import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.schemas.installation import InstallationSession, InstallationStatusResponse
from app.schemas.application import Application

# Dead JobManager code removed

class InstallationService:
    @staticmethod
    def create_and_start_installation(db, application_id: str, application_name: str, host_id: str, version: str, applications: list = None, job_id: str = None, requester_email: str = None) -> str:
        import uuid
        from app.database.repositories.job_repository import job_repo
        from app.services.queue_service import QueueService
        
        if not job_id:
            job_id = f"job_{str(uuid.uuid4())[:8]}"
            job_data = {
                "id": job_id,
                "application_id": application_id,
                "host_id": str(host_id),
                "status": "QUEUED"
            }
            job_repo.create(db, obj_in=job_data)
        else:
            job = job_repo.get(db, job_id)
            if job:
                job_repo.update(db, db_obj=job, obj_in={"status": "QUEUED", "host_id": str(host_id)})
        
        QueueService.enqueue_installation(
            job_id=job_id,
            application_name=application_name,
            version=version,
            applications=applications,
            host_ids=[int(host_id)] if str(host_id).isdigit() else [1],
            requester_email=requester_email
        )
        return job_id
