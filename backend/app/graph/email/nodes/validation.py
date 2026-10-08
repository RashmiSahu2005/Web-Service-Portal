from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.application_service import ApplicationService
from app.services.fleetdm_service import FleetDMService
from app.database.database import SessionLocal
import email.utils

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
            
        host_info = None
        requested_target = ip_addr
        
        if ip_addr:
            host_info = FleetDMService.verify_host_enrolled(ip_addr)
        
        if not host_info:
            # If no IP was extracted or not found, try username
            _, sender_email = email.utils.parseaddr(state.get("sender", ""))
            if sender_email:
                username = sender_email.split("@")[0]
                logger.info(f"[EmailGraph] Trying host verification by sender username: '{username}'")
                host_info = FleetDMService.verify_host_enrolled(username)
                if not requested_target:
                    requested_target = username
                
            if not host_info:
                # Host NOT found in FleetDM — structured failure and email to requester
                target_desc = requested_target or (sender_email if sender_email else "unknown host")
                logger.warning(f"[EmailGraph] Requested host '{target_desc}' NOT found/enrolled in FleetDM. Failing with HOST_NOT_FOUND_IN_FLEET.")
                
                requester_email = sender_email or state.get("requester_email")
                if requester_email:
                    from app.services.email_service import EmailService
                    EmailService.send_host_not_found_email(
                        recipient_email=requester_email,
                        requested_host=str(target_desc),
                        in_reply_to=state.get("message_id")
                    )
                
                return {
                    **state,
                    "application_id": app.id,
                    "status": "HOST_NOT_FOUND_IN_FLEET",
                    "failure_category": "HOST_NOT_FOUND_IN_FLEET",
                    "error_message": f"The requested host {target_desc} was not found in FleetDM. No installation/update was performed."
                }
                
        logger.info(f"[EmailGraph] Validation successful. Enrolled host verified: ID={host_info.get('id')}. Transitioning to PENDING_APPROVAL.")
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
