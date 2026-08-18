from pydantic import BaseModel
from typing import List

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

class InstallationStatusResponse(BaseModel):
    step: str
    status: str
    percentage: int
    message: str
    logs: List[str]
    estimated_time: str
