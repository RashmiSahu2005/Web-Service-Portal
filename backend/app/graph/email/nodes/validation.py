from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.application_service import ApplicationService
from app.services.fleetdm_service import FleetDMService
from app.database.database import SessionLocal

def validate_request(state: EmailState) -> EmailState:
    logger.info(f"[EmailGraph] Validating request: {state.get('message_id')}")
    
    if state.get("status") != "RECEIVED" or not state.get("application_name"):
        return state

    app_name = state.get("application_name")
    ip_addr = state.get("target_host_ip")

    db = SessionLocal()
    try:
        apps = ApplicationService.get_all_applications(db)
        app = next((a for a in apps if a.name.lower() == app_name.lower()), None)
        
        if not app:
            logger.info(f"[EmailGraph] Application '{app_name}' not found. Auto-registering it dynamically.")
            import uuid
            from app.schemas.application import ApplicationCreate, Application as ApplicationSchema
            
            app_id = str(uuid.uuid4())
            new_app = ApplicationCreate(
                name=app_name,
                category="Auto-Generated",
                description=f"Auto-registered via Email Request",
                supported_os=["Ubuntu", "Windows", "macOS"]
            )
            app = ApplicationSchema(id=app_id, **new_app.model_dump())
            ApplicationService.add_application(db, app)
            logger.info(f"[EmailGraph] Successfully auto-registered '{app_name}' with ID: {app_id}")
            
        host_info = FleetDMService.get_host_info(ip_addr)
        if not host_info:
            logger.warning(f"[EmailGraph] Target host IP '{ip_addr}' not found in FleetDM.")
            return {**state, "status": "INVALID", "error_message": f"Host '{ip_addr}' not found."}
            
        logger.info(f"[EmailGraph] Validation successful. Transitioning to PENDING_APPROVAL.")
        return {
            **state,
            "application_id": app.id,
            "host_id": str(host_info.get("id")),
            "status": "PENDING_APPROVAL"
        }
    except Exception as e:
        logger.error(f"[EmailGraph] Validation error: {str(e)}")
        return {**state, "status": "INVALID", "error_message": str(e)}
    finally:
        db.close()
