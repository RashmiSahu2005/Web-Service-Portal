# pyrefly: ignore [missing-import]
from celery import Celery
from app.core.config import settings
from app.core.logger import logger

try:
    celery_app = Celery(
        "installation_worker",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["app.tasks.installation_tasks"]
    )
    
    # Configure Celery
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
    )
    logger.info("Celery application initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Celery application: {e}")
    celery_app = None
