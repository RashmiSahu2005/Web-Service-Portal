from pydantic import BaseModel
from typing import List, Optional

class ApplicationBase(BaseModel):
    name: str
    version: str
    category: str
    description: Optional[str] = ""
    package_name: Optional[str] = ""
    package_path: Optional[str] = ""
    installer_type: str
    install_command: str
    package_size: Optional[str] = "Unknown"
    checksum: Optional[str] = "Pending..."
    dependencies: Optional[List[str]] = []
    supported_os: Optional[List[str]] = ["Ubuntu"]
    estimated_install_time: Optional[str] = "Unknown"
    notify_admin: Optional[bool] = False
    minimum_battery_percentage: int
    retry_limit: int
    email_notification: bool
    auto_remediation: bool
    status: Optional[str] = "ACTIVE"

class Application(ApplicationBase):
    id: str

class ApplicationCreate(ApplicationBase):
    pass
