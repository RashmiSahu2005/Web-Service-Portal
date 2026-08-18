from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
import datetime
from app.database.database import Base

class ApplicationStrategy(Base):
    __tablename__ = "application_strategies"

    strategy_id = Column(Integer, primary_key=True, index=True)
    application_name = Column(String, index=True)
    operating_system = Column(String, index=True)
    os_version = Column(String, index=True, nullable=True)
    architecture = Column(String, index=True)
    
    package_manager = Column(String, nullable=True)
    package_name = Column(String, nullable=True)
    installation_method = Column(String)
    
    installed_version_command = Column(JSON)
    latest_version_command = Column(JSON, nullable=True)
    latest_version_source = Column(String, nullable=True)
    verification_command = Column(JSON)
    
    strategy_status = Column(String, default="ACTIVE")
    strategy_hash = Column(String, unique=True, index=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    last_validated_at = Column(DateTime, nullable=True)
    failure_count = Column(Integer, default=0)
