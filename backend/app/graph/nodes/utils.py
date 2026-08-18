from datetime import datetime
from app.services.agent_event_service import AgentEventService
from app.core.logger import logger

def broadcast_stage(job_id: str, agent: str, stage: str, status: str):
    if not job_id:
        return
    AgentEventService.broadcast_agent_stage(
        job_id=job_id,
        agent=agent,
        stage=stage,
        status=status,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )

def broadcast_log(job_id: str, agent: str, message: str, level: str = "info"):
    if level == "error":
        logger.error(message, stacklevel=2)
    elif level == "warning":
        logger.warning(message, stacklevel=2)
    else:
        logger.info(message, stacklevel=2)
        
    if job_id:
        full_msg = f"[{agent}] {message}"
        AgentEventService.broadcast_agent_log(job_id, full_msg)
