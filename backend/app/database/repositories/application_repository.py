from app.database.repositories.base import BaseRepository
from app.database.models.application import Application
from sqlalchemy.orm import Session

class ApplicationRepository(BaseRepository[Application]):
    def __init__(self):
        super().__init__(Application)

application_repo = ApplicationRepository()
