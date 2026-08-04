from fastapi import APIRouter
from typing import List
from app.schemas.application import Application, ApplicationCreate
from app.services.application_service import ApplicationService

router = APIRouter()

@router.get("/admin/applications", response_model=List[Application])
def get_admin_applications():
    return ApplicationService.get_all_applications()

@router.post("/admin/applications", response_model=Application)
def create_admin_application(app_create: ApplicationCreate):
    import uuid
    
    app_dict = app_create.dict()
    
    new_app = Application(
        id=f"app_{str(uuid.uuid4())[:8]}",
        **app_dict
    )
    ApplicationService.add_application(new_app)
    return new_app

from fastapi import HTTPException

@router.get("/admin/applications/{app_id}", response_model=Application)
def get_admin_application(app_id: str):
    app = ApplicationService.get_application(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.put("/admin/applications/{app_id}", response_model=Application)
def update_admin_application(app_id: str, app_update: ApplicationCreate):
    existing_app = ApplicationService.get_application(app_id)
    if not existing_app:
        raise HTTPException(status_code=404, detail="Application not found")
    
    app_dict = app_update.dict()
    updated_app = Application(
        id=app_id,
        **app_dict
    )
    result = ApplicationService.update_application(app_id, updated_app)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to update application")
    return result

@router.delete("/admin/applications/{app_id}")
def delete_admin_application(app_id: str):
    success = ApplicationService.delete_application(app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"status": "success", "message": "Application deleted successfully"}
