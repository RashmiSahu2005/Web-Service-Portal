import redis
import json
from typing import Optional, Dict
from app.core.config import settings
from app.core.logger import logger

class RedisService:
    def __init__(self):
        try:
            self.client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            self.client.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None

    def get_latest_version(self, application_name: str, os_name: str, architecture: str) -> Optional[Dict]:
        if not self.client:
            return None
            
        key = f"applicationhub:latest_version:{application_name.lower()}:{os_name.lower()}:{architecture.lower()}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error fetching from Redis cache: {e}")
        return None

    def set_latest_version(self, application_name: str, os_name: str, architecture: str, version_data: Dict) -> bool:
        if not self.client:
            return False
            
        key = f"applicationhub:latest_version:{application_name.lower()}:{os_name.lower()}:{architecture.lower()}"
        ttl_seconds = settings.LATEST_VERSION_CACHE_TTL_HOURS * 3600
        
        try:
            self.client.setex(key, ttl_seconds, json.dumps(version_data))
            return True
        except Exception as e:
            logger.error(f"Error writing to Redis cache: {e}")
            return False

    # ── Installation Research Cache ──────────────────────────────────────────
    # Separate from the Script Registry (which stores proven executable scripts).
    # This cache stores installation *knowledge* with a shorter TTL.

    def get_research_result(self, canonical_app: str, version: str, os_name: str, architecture: str) -> Optional[Dict]:
        """Retrieve a cached installation research result. Returns None on miss or error."""
        if not self.client:
            return None
        key = f"deployiq:research:{canonical_app.lower()}:{version.lower()}:{os_name.lower()}:{architecture.lower()}"
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"[ResearchCache] Error reading research cache: {e}")
        return None

    def set_research_result(self, canonical_app: str, version: str, os_name: str, architecture: str, result: Dict) -> bool:
        """Cache an installation research result. Returns True on success."""
        if not self.client:
            return False
        key = f"deployiq:research:{canonical_app.lower()}:{version.lower()}:{os_name.lower()}:{architecture.lower()}"
        ttl_seconds = settings.INSTALLATION_RESEARCH_CACHE_TTL_HOURS * 3600
        try:
            self.client.setex(key, ttl_seconds, json.dumps(result))
            return True
        except Exception as e:
            logger.error(f"[ResearchCache] Error writing research cache: {e}")
            return False

# Global instance for use in nodes
redis_service = RedisService()
