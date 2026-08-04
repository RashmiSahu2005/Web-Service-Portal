from typing import List, Optional
from app.schemas.application import Application
# pyrefly: ignore [missing-import]
from app.services.package_repository import package_repo

class ApplicationService:
    @staticmethod
    def get_all_applications() -> List[Application]:
        return package_repo.get_all_packages()

    @staticmethod
    def get_application(app_id: str) -> Optional[Application]:
        return package_repo.get_package_by_id(app_id)

    @staticmethod
    def add_application(app: Application):
        package_repo.add_package(app)

    @staticmethod
    def update_application(app_id: str, app_update: Application) -> Optional[Application]:
        return package_repo.update_package(app_id, app_update)

    @staticmethod
    def delete_application(app_id: str) -> bool:
        return package_repo.delete_package(app_id)
