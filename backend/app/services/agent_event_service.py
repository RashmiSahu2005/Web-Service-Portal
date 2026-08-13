import asyncio
from typing import Dict, Any, List, Optional
from app.core.logger import logger

class AgentEventService:
    """
    Helper service to safely broadcast agent events to the existing WebSocket manager.
    Any failure during broadcasting is swallowed to prevent breaking the installation flow.
    """

    @staticmethod
    def _safe_broadcast(job_id: str, payload: dict):
        if not job_id:
            return

        import redis
        import json
        from app.core.config import settings

        try:
            r = redis.Redis(host='localhost', port=6379, db=0)
            r.publish(f"installation_{job_id}", json.dumps(payload))
        except Exception as e:
            logger.warning(f"Failed to publish to redis for job {job_id}: {e}")

    @staticmethod
    def broadcast_agent_stage(job_id: str, agent: str, stage: str, status: str, timestamp: str):
        payload = {
            "type": "agent_stage",
            "job_id": job_id,
            "agent": agent,
            "stage": stage,
            "status": status,
            "timestamp": timestamp
        }
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_agent_log(job_id: str, log_line: str):
        # We reuse the existing 'log' type for backwards compatibility with the UI
        payload = {
            "type": "log",
            "message": log_line
        }
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_risk(job_id: str, risk_score: int, risk_level: str, risk_reasons: List[str]):
        payload = {
            "type": "risk_analysis",
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_reasons": risk_reasons
        }
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_host_info(job_id: str, host_ids: List[int], hostname: Optional[str] = None, ip_address: Optional[str] = None):
        payload = {
            "type": "host_discovery",
            "host_ids": host_ids
        }
        if hostname:
            payload["hostname"] = hostname
        if ip_address:
            payload["ip_address"] = ip_address
        AgentEventService._safe_broadcast(job_id, payload)
        
    @staticmethod
    def broadcast_fleet_execution(job_id: str, script_id: str, execution_ids: List[str], host_ids: List[int]):
        payload = {
            "type": "fleet_execution",
            "script_id": script_id,
            "execution_ids": execution_ids,
            "host_ids": host_ids
        }
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_verification(job_id: str, verification_result: bool, verification_results: Dict[str, bool]):
        payload = {
            "type": "verification",
            "verification_result": verification_result,
            "verification_results": verification_results
        }
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_notification_status(job_id: str, email_sent: bool, status: str):
        payload = {
            "type": "notification",
            "email_sent": email_sent,
            "status": status
        }
        AgentEventService._safe_broadcast(job_id, payload)
        
    @staticmethod
    def broadcast_installation_complete(job_id: str, status: str, error: Optional[str] = None):
        payload = {
            "type": "installation_complete",
            "status": status
        }
        if error:
            payload["error"] = error
        AgentEventService._safe_broadcast(job_id, payload)

    @staticmethod
    def broadcast_application_state(job_id: str, application_states: dict, installed_versions: dict, available_versions: dict):
        payload = {
            "type": "application_state_result",
            "application_states": application_states,
            "installed_versions": installed_versions,
            "available_versions": available_versions
        }
        AgentEventService._safe_broadcast(job_id, payload)

