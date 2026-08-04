from typing import Dict, List, Optional
import datetime

class RetryManager:
    def __init__(self):
        # Format: { "installation_id": { "current_retry": 0, "max_retries": 3, "previous_failures": [] } }
        self.state: Dict[str, Dict] = {}

    def initialize_session(self, session_id: str, max_retries: int):
        self.state[session_id] = {
            "current_retry": 0,
            "max_retries": max_retries,
            "previous_failures": []
        }

    def record_failure(self, session_id: str, failure_reason: str):
        if session_id not in self.state:
            return
        
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.state[session_id]["previous_failures"].append({
            "reason": failure_reason,
            "timestamp": timestamp
        })
        self.state[session_id]["current_retry"] += 1

    def can_retry(self, session_id: str) -> bool:
        if session_id not in self.state:
            return False
        return self.state[session_id]["current_retry"] < self.state[session_id]["max_retries"]

    def get_current_retry(self, session_id: str) -> int:
        if session_id not in self.state:
            return 0
        return self.state[session_id]["current_retry"]

retry_manager = RetryManager()
