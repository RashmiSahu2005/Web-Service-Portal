from fastapi import APIRouter, Depends, HTTPException
from typing import List
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session
from app.schemas.application import Application, ApplicationCreate
from app.services.application_service import ApplicationService
from app.database.database import get_db
from app.core.config import settings

router = APIRouter()

@router.get("/admin/applications", response_model=List[Application])
def get_admin_applications(db: Session = Depends(get_db)):
    return ApplicationService.get_all_applications(db)

@router.post("/admin/applications", response_model=Application)
def create_admin_application(app_create: ApplicationCreate, db: Session = Depends(get_db)):
    import uuid
    
    app_dict = app_create.model_dump()
    if not app_dict.get("version") or not app_dict["version"].strip():
        app_dict["version"] = "latest"
    
    new_app = Application(
        id=f"app_{str(uuid.uuid4())[:8]}",
        **app_dict
    )
    ApplicationService.add_application(db, new_app)
    return new_app

@router.get("/admin/applications/{app_id}", response_model=Application)
def get_admin_application(app_id: str, db: Session = Depends(get_db)):
    app = ApplicationService.get_application(db, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app

@router.put("/admin/applications/{app_id}", response_model=Application)
def update_admin_application(app_id: str, app_update: ApplicationCreate, db: Session = Depends(get_db)):
    existing_app = ApplicationService.get_application(db, app_id)
    if not existing_app:
        raise HTTPException(status_code=404, detail="Application not found")
    app_dict = app_update.model_dump()
    if not app_dict.get("version") or not app_dict["version"].strip():
        app_dict["version"] = "latest"
    updated_app = Application(
        id=app_id,
        **app_dict
    )
    result = ApplicationService.update_application(db, app_id, updated_app)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to update application")
    return result

@router.delete("/admin/applications/{app_id}")
def delete_admin_application(app_id: str, db: Session = Depends(get_db)):
    success = ApplicationService.delete_application(db, app_id)
    if not success:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"status": "success", "message": "Application deleted successfully"}
