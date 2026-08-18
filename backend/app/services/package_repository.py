from typing import List, Optional
from app.schemas.application import Application
from app.utils.dummy_data import DUMMY_APPLICATIONS

class PackageRepository:
    def __init__(self):
        # In a real app, this would connect to a database or actual repository
        self.applications = DUMMY_APPLICATIONS

    def get_all_packages(self) -> List[Application]:
        return self.applications

    def get_package_by_id(self, package_id: str) -> Optional[Application]:
        for app in self.applications:
            if app.id == package_id:
                return app
        return None

    def verify_checksum(self, package_id: str, checksum: str) -> bool:
        app = self.get_package_by_id(package_id)
        if app:
            return app.checksum == checksum
        return False

    def get_dependencies(self, package_id: str) -> List[str]:
        app = self.get_package_by_id(package_id)
        if app:
            return app.dependencies
        return []

    def add_package(self, app: Application):
        self.applications.append(app)

    def update_package(self, package_id: str, app_update: Application) -> Optional[Application]:
        for idx, app in enumerate(self.applications):
            if app.id == package_id:
                # Keep the same ID, update the rest
                updated_app = app_update.copy(update={"id": package_id})
                self.applications[idx] = updated_app
                return updated_app
        return None

    def delete_package(self, package_id: str) -> bool:
        for idx, app in enumerate(self.applications):
            if app.id == package_id:
                self.applications.pop(idx)
                return True
        return False

# Singleton instance
package_repo = PackageRepository()
