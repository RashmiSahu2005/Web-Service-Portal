from pydantic import BaseModel
from typing import List, Optional

class ApplicationBase(BaseModel):
    name: str
    version: str
    category: str
    description: Optional[str] = ""
    fleet_script_id: Optional[str] = None
    package_name: Optional[str] = ""
    package_path: Optional[str] = ""
    package_type: Optional[str] = ""
    installer_type: Optional[str] = "apt"
    install_command: Optional[str] = ""
    package_size: Optional[str] = "Unknown"
    checksum: Optional[str] = "Pending..."
    dependencies: Optional[List[str]] = []
    supported_os: Optional[List[str]] = ["Ubuntu"]
    estimated_install_time: Optional[str] = "Unknown"
    notify_admin: Optional[bool] = False
    battery_threshold: Optional[int] = 30
    minimum_battery_percentage: Optional[int] = 30
    retry_limit: Optional[int] = 3
    email_enabled: Optional[bool] = False
    email_notification: Optional[bool] = False
    auto_remediation: Optional[bool] = False
    status: Optional[str] = "ACTIVE"
    
    class Config:
        from_attributes = True

class Application(ApplicationBase):
    id: str

class ApplicationCreate(ApplicationBase):
    pass
