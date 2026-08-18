import logging
import os
import contextvars
from datetime import datetime


# ============================================================
# JOB CONTEXT
# ============================================================

current_job_id = contextvars.ContextVar(
    "current_job_id",
    default=None
)


class JobContextFilter(logging.Filter):
    """Adds the current job_id to every log record."""

    def filter(self, record):
        record.job_id = current_job_id.get()
        return True


class JobIdFilter(logging.Filter):
    """Allows only logs belonging to a specific job."""

    def __init__(self, target_job_id: str):
        super().__init__()
        self.target_job_id = target_job_id

    def filter(self, record):
        return getattr(record, "job_id", None) == self.target_job_id


# ============================================================
# LOG FORMAT
# ============================================================

# IMPORTANT:
# %(msecs)03d gives:
# 120
# 443
# 005
#
# Result:
# [2026-06-25 17:22:18,120] INFO | file.py:33 | Message

LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [File: %(filename)s] [Line: %(lineno)d] - %(message)s"
)

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ============================================================
# MAIN LOGGER
# ============================================================

logger = logging.getLogger("ApplicationHub")

logger.setLevel(logging.INFO)

# Prevent duplicate logs
logger.propagate = False


# Remove existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)


# Add job context filter
logger.addFilter(JobContextFilter())


# ============================================================
# CONSOLE HANDLER
# ============================================================

console_handler = logging.StreamHandler()

console_handler.setLevel(logging.INFO)

console_handler.setFormatter(
    logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT
    )
)

logger.addHandler(console_handler)


# ============================================================
# SET CURRENT JOB
# ============================================================

def set_current_job(job_id: str):
    """
    Set the job_id for the current async/context execution.
    """

    return current_job_id.set(job_id)


def reset_current_job(token):
    """
    Reset the previous job context.
    """

    current_job_id.reset(token)


# ============================================================
# CREATE JOB LOG FILE
# ============================================================

def setup_job_logger(job_id: str) -> logging.FileHandler:
    """
    Create a dedicated .log file for one installation job.

    Structure:

        logs/
            YYYY-MM-DD_HH-MM-SS_job_<job_id>.log
    """

    # Project root / existing logs directory
    project_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            ".."
        )
    )

    log_dir = os.path.join(
        project_root,
        "logs"
    )

    os.makedirs(
        log_dir,
        exist_ok=True
    )

    # Timestamp
    now = datetime.now()

    timestamp = now.strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    # Example:
    # 2026-08-10_12-35-42_job_75029afc.log

    log_filename = (
        f"{timestamp}_job_{job_id}.log"
    )

    log_filepath = os.path.join(
        log_dir,
        log_filename
    )

    # Create file handler
    file_handler = logging.FileHandler(
        log_filepath,
        mode="a",
        encoding="utf-8"
    )

    file_handler.setLevel(
        logging.INFO
    )

    file_handler.setFormatter(
        logging.Formatter(
            LOG_FORMAT,
            datefmt=DATE_FORMAT
        )
    )

    # Only this job's logs go into this file
    file_handler.addFilter(
        JobIdFilter(job_id)
    )

    logger.addHandler(
        file_handler
    )

    return file_handler


# ============================================================
# REMOVE JOB LOGGER
# ============================================================

def remove_job_logger(
    file_handler: logging.FileHandler
):
    """
    Remove and close the job-specific log handler.
    """

    if file_handler:

        logger.removeHandler(
            file_handler
        )

        file_handler.close()