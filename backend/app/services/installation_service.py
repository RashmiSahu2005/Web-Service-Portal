import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.schemas.installation import InstallationSession, InstallationStatusResponse
# pyrefly: ignore [missing-import]
from app.services.package_repository import package_repo
from app.services.retry_service import retry_manager
from app.schemas.application import Application

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, InstallationSession] = {}

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")
        
    def _log(self, session: InstallationSession, message: str):
        log_line = f"{self._get_timestamp()} {message}"
        session.logs.append(log_line)
        return log_line

    def create_job(self, application_id: str) -> str:
        job_id = str(uuid.uuid4())
        app = package_repo.get_package_by_id(application_id)
        
        session = InstallationSession(
            installation_id=job_id,
            application_id=application_id,
            current_step="Request Received",
            status="PENDING",
            percentage=0,
            logs=[f"{self._get_timestamp()} Request Received for {app.name if app else application_id}. Waiting for agent..."],
            estimated_time=app.estimated_install_time if app else "Unknown"
        )
        self.jobs[job_id] = session
        
        # Initialize retries
        retry_manager.initialize_session(job_id, max_retries=app.retry_limit if app else 3)
        return job_id

    def get_pending_job(self) -> Optional[Dict[str, Any]]:
        """Used by the Linux Agent to pull the next pending job."""
        for job_id, session in self.jobs.items():
            if session.status == "PENDING":
                app = package_repo.get_package_by_id(session.application_id)
                if app:
                    session.status = "RUNNING"
                    self._log(session, "Agent assigned to job.")
                    return {
                        "job_id": job_id,
                        "application_id": app.id,
                        "package_path": app.package_path,
                        "install_command": app.install_command,
                        "minimum_battery": app.minimum_battery_percentage
                    }
        return None

    def update_job_status(self, job_id: str, status: str, step: str, percentage: int):
        session = self.jobs.get(job_id)
        if session:
            session.status = status
            session.current_step = step
            session.percentage = percentage

    def append_job_log(self, job_id: str, message: str) -> Optional[str]:
        session = self.jobs.get(job_id)
        if session:
            return self._log(session, message)
        return None

    def get_status(self, job_id: str) -> InstallationStatusResponse:
        session = self.jobs.get(job_id)
        if not session:
            return InstallationStatusResponse(
                step="Unknown",
                status="FAILED",
                percentage=0,
                message="Session not found",
                logs=[],
                estimated_time=""
            )

        return InstallationStatusResponse(
            step=session.current_step,
            status=session.status,
            percentage=session.percentage,
            message=session.logs[-1] if session.logs else "",
            logs=session.logs,
            estimated_time=session.estimated_time
        )

# Singleton instance
installation_manager = JobManager()

class InstallationService:
    @staticmethod
    def create_and_start_installation(db, application_id: str, application_name: str, host_id: str, version: str, job_id: str = None) -> str:
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
            host_ids=[int(host_id)] if str(host_id).isdigit() else [1]
        )
        return job_id
