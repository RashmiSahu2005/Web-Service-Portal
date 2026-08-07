from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base

class InstallationJob(Base):
    __tablename__ = "installation_jobs"

    id = Column(String, primary_key=True, index=True)
    application_id = Column(String, ForeignKey("applications.id"))
    host_id = Column(String)
    status = Column(String, default="PENDING")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    exit_code = Column(Integer, nullable=True)

    logs = relationship("InstallationLog", back_populates="job")

class InstallationLog(Base):
    __tablename__ = "installation_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(String, ForeignKey("installation_jobs.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    log_level = Column(String, default="INFO")
    message = Column(String)

    job = relationship("InstallationJob", back_populates="logs")
