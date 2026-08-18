from fastapi import APIRouter, HTTPException
from app.schemas.installation import InstallationStatusResponse
from app.services.installation_service import installation_manager
# pyrefly: ignore [missing-import]
from app.services.package_repository import package_repo
from pydantic import BaseModel

router = APIRouter()

class InstallResponse(BaseModel):
    installation_id: str

@router.post("/install/{application_id}", response_model=InstallResponse)
async def request_installation(application_id: str):
    app = package_repo.get_package_by_id(application_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    session_id = installation_manager.create_session(application_id)
    return InstallResponse(installation_id=session_id)

@router.get("/install/{installation_id}", response_model=InstallationStatusResponse)
def get_installation_status(installation_id: str):
    return installation_manager.get_status(installation_id)
