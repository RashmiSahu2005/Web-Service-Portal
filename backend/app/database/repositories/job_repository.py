from app.database.repositories.base import BaseRepository
from app.database.models.job import InstallationJob, InstallationLog
from sqlalchemy.orm import Session

class JobRepository(BaseRepository[InstallationJob]):
    def __init__(self):
        super().__init__(InstallationJob)

job_repo = JobRepository()

class LogRepository(BaseRepository[InstallationLog]):
    def __init__(self):
        super().__init__(InstallationLog)
        
    def get_by_job_id(self, db: Session, job_id: str):
        return db.query(self.model).filter(self.model.job_id == job_id).all()

log_repo = LogRepository()
