# pyrefly: ignore [missing-import]
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from datetime import datetime
from app.database.database import Base

class InstallationHistory(Base):
    __tablename__ = "installation_history"

    id = Column(String, primary_key=True, index=True)
    application_id = Column(String, ForeignKey("applications.id"))
    host_id = Column(String)
    result = Column(String)
    duration = Column(Integer)  # in seconds
    installed_at = Column(DateTime, default=datetime.utcnow)
