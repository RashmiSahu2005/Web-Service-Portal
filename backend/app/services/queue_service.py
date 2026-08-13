from app.core.logger import logger
# pyrefly: ignore [missing-import]
from app.services.celery_app import celery_app
from app.tasks.installation_tasks import run_installation_job

class QueueService:
    @staticmethod
    def enqueue_installation(job_id: str, application_name: str = None, version: str = None, host_ids: list = None) -> str:
        # Note: Celery only needs job_id. Extra parameters kept for interface compatibility.
        logger.info(f"Enqueueing Celery task for job {job_id}...")
        try:
            task = run_installation_job.delay(job_id)
            return str(task.id)
        except Exception as e:
            logger.error(f"Failed to enqueue Celery task: {e}")
            raise RuntimeError(f"Celery enqueue failed: {e}")
