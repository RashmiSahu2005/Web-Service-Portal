from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.installation_service import InstallationService
from app.database.database import SessionLocal

def map_to_installation(state: EmailState) -> EmailState:
    logger.info(f"[EmailGraph] Mapping approved request to installation: {state.get('message_id')}")
    
    if state.get("status") != "APPROVED":
        return state
        
    application_id = state.get("application_id")
    application_name = state.get("application_name")
    applications = state.get("applications", [{"name": application_name, "version": state.get("version", "Latest")}])
    host_id = state.get("host_id")
    version = state.get("version", "Latest")
    requester_email = state.get("requester_email")
    
    if not host_id or not applications:
        logger.error("[EmailGraph] Missing required installation variables in state.")
        return {**state, "status": "FAILED", "error_message": "Missing variables for mapping."}
        
    db = SessionLocal()
    try:
        job_id = InstallationService.create_and_start_installation(
            db=db,
            application_id=application_id,
            application_name=application_name,
            applications=applications,
            host_id=host_id,
            version=version,
            requester_email=requester_email
        )
        logger.info(f"[EmailGraph] Successfully created and queued installation job: {job_id}")
        return {
            **state,
            "status": "COMPLETED",
            "job_id": job_id
        }
    except Exception as e:
        logger.error(f"[EmailGraph] Failed to map request to installation: {str(e)}")
        return {**state, "status": "FAILED", "error_message": str(e)}
    finally:
        db.close()
