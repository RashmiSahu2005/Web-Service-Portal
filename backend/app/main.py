from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import applications, installation, admin
from app.core.config import settings
from app.core.logger import logger

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Internal Enterprise Self-Service Software Portal (MVP)",
    version="0.1.0"
)

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(applications.router, tags=["applications"])
app.include_router(installation.router, tags=["installation"])
app.include_router(admin.router, tags=["admin"])

from app.database.database import Base, engine
from app.database import models

@app.on_event("startup")
async def startup_event():
    logger.info("Application Hub MVP backend started.")
    # Create SQLite tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized.")
    
    # Log configuration mode
    logger.info(f"[CONFIG] USE_FLEETDM={str(settings.USE_FLEETDM).lower()}")
    if settings.USE_FLEETDM:
        logger.info("[CONFIG] Agentic installation mode: REAL FLEETDM")
    else:
        logger.info("[CONFIG] Agentic installation mode: LEGACY SIMULATION")
        
    # Start Email Listener if enabled
    if getattr(settings, 'ENABLE_IMAP_LISTENER', False):
        from app.mail_listener.email_listener import start_polling
        start_polling()

@app.get("/")
def read_root():
    return {"message": "Welcome to the Application Hub API"}
