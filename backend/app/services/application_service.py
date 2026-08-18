from typing import List, Optional
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from app.schemas.application import Application as ApplicationSchema, ApplicationCreate
from app.database.repositories.application_repository import application_repo

class ApplicationService:
    @staticmethod
    def get_all_applications(db: Session) -> List[ApplicationSchema]:
        apps = application_repo.get_all(db)
        return [ApplicationSchema.model_validate(app) for app in apps]

    @staticmethod
    def get_application(db: Session, app_id: str) -> Optional[ApplicationSchema]:
        app = application_repo.get(db, app_id)
        if app:
            return ApplicationSchema.model_validate(app)
        return None

    @staticmethod
    def add_application(db: Session, app: ApplicationSchema):
        app_data = app.model_dump()
        application_repo.create(db, obj_in=app_data)

    @staticmethod
    def update_application(db: Session, app_id: str, app_update: ApplicationSchema) -> Optional[ApplicationSchema]:
        app_obj = application_repo.get(db, app_id)
        if app_obj:
            updated = application_repo.update(db, db_obj=app_obj, obj_in=app_update.model_dump(exclude_unset=True))
            return ApplicationSchema.model_validate(updated)
        return None

    @staticmethod
    def delete_application(db: Session, app_id: str) -> bool:
        return application_repo.delete(db, id=app_id)
