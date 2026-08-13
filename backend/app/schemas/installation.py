from pydantic import BaseModel
from typing import List, Optional

class InstallationStep(BaseModel):
    step_number: int
    step_name: str
    status: str
    message: str
    percentage: int
    timestamp: str

class InstallationSession(BaseModel):
    installation_id: str
    application_id: str
    current_step: str
    status: str
    percentage: int
    logs: List[str]
    estimated_time: str
    
    class Config:
        from_attributes = True

class InstallationStatusResponse(BaseModel):
    step: str
    status: str
    percentage: int
    message: str
    logs: List[str]
    estimated_time: str
    device_readiness: Optional[dict] = None
    risk_score: Optional[int] = None
    risk_level: Optional[str] = None
    risk_reasons: Optional[List[str]] = None
    host_ids: Optional[List[int]] = None
    current_stage: Optional[str] = None
    execution_ids: Optional[List[str]] = None
    verification_result: Optional[bool] = None
    email_sent: Optional[bool] = None
