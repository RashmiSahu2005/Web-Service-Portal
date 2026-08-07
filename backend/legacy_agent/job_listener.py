import requests
from agent.config import BACKEND_URL
from agent.logger import get_logger

logger = get_logger("job_listener")

def poll_pending_job():
    try:
        resp = requests.get(f"{BACKEND_URL}/jobs/pending")
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Failed to poll jobs: {e}")
    return None

def send_log(job_id: str, message: str):
    try:
        requests.post(f"{BACKEND_URL}/jobs/{job_id}/logs", json={"message": message})
    except Exception as e:
        logger.error(f"Failed to send log: {e}")

def update_status(job_id: str, status: str, step: str, percentage: int):
    try:
        requests.post(
            f"{BACKEND_URL}/jobs/{job_id}/status", 
            json={"status": status, "step": step, "percentage": percentage}
        )
    except Exception as e:
        logger.error(f"Failed to update status: {e}")
