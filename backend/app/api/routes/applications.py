from fastapi import APIRouter
from typing import List
from app.schemas.application import Application
from app.services.application_service import ApplicationService

router = APIRouter()

@router.get("/applications", response_model=List[Application])
def get_applications():
    return ApplicationService.get_all_applications()
