from app.database.repositories.base import BaseRepository
from app.database.models.history import InstallationHistory
from sqlalchemy.orm import Session

class HistoryRepository(BaseRepository[InstallationHistory]):
    def __init__(self):
        super().__init__(InstallationHistory)

history_repo = HistoryRepository()
