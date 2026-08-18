from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.sql import func
from app.database.database import Base

class ScriptRegistry(Base):
    __tablename__ = "script_registry"
    
    registry_id = Column(Integer, primary_key=True, index=True)
    application_name = Column(String, index=True)
    version = Column(String, index=True)
    operating_system = Column(String)
    architecture = Column(String)
    
    fleet_script_id = Column(String)
    script_hash = Column(String)
    
    risk_score = Column(Integer)
    risk_level = Column(String)
    risk_reasons = Column(JSON, default=list)
    
    status = Column(String, default="ACTIVE") # ACTIVE, INVALID
    failure_count = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
