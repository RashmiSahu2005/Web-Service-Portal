from sqlalchemy import Column, String, Boolean, Integer, DateTime, JSON
from datetime import datetime
from app.database.database import Base

class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String)
    fleet_script_id = Column(String)
    package_name = Column(String)
    package_path = Column(String)
    package_type = Column(String)
    installer_type = Column(String)
    install_command = Column(String)
    package_size = Column(String)
    checksum = Column(String)
    dependencies = Column(JSON)
    supported_os = Column(JSON)
    estimated_install_time = Column(String)
    notify_admin = Column(Boolean, default=False)
    battery_threshold = Column(Integer, default=30)
    minimum_battery_percentage = Column(Integer, default=30)
    retry_limit = Column(Integer, default=3)
    email_enabled = Column(Boolean, default=False)
    email_notification = Column(Boolean, default=False)
    auto_remediation = Column(Boolean, default=False)
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
