from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session
from app.schemas.application import Application
from app.services.application_service import ApplicationService
from app.database.database import get_db

router = APIRouter()

@router.get("/applications", response_model=List[Application])
def get_applications(db: Session = Depends(get_db)):
    return ApplicationService.get_all_applications(db)
