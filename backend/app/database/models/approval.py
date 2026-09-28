from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.sql import func
from app.database.database import Base
import uuid

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, index=True, nullable=False)
    application = Column(String, nullable=False)
    host_id = Column(String, nullable=False)
    hostname = Column(String, nullable=False)
    
    original_requester_email = Column(String, nullable=False)
    original_message_id = Column(String, nullable=True)
    original_thread_id = Column(String, nullable=True)
    
    current_version = Column(String, nullable=True)
    target_version = Column(String, nullable=True)
    approval_reason = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False)
    
    os_signature = Column(String, nullable=False)
    update_strategy = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String, nullable=True)
