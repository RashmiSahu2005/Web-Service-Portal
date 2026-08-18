import asyncio
import uuid
import random
from typing import Dict, Any, List, Tuple
from datetime import datetime

from app.schemas.installation import InstallationSession, InstallationStatusResponse
# pyrefly: ignore [missing-import]
from app.services.package_repository import package_repo
from app.services.validation_service import ValidationService
from app.services.battery_service import BatteryService
from app.services.email_service import EmailService
from app.services.error_parser import ErrorParser, ErrorType
from app.services.remediation_service import RemediationService
from app.services.retry_service import retry_manager

class InstallationManager:
    def __init__(self):
        self.sessions: Dict[str, InstallationSession] = {}

    def _get_timestamp(self) -> str:
        return datetime.now().strftime("[%H:%M:%S]")
        
    def _log(self, session: InstallationSession, message: str):
        session.logs.append(f"{self._get_timestamp()} {message}")

    def create_session(self, application_id: str) -> str:
        session_id = str(uuid.uuid4())
        app = package_repo.get_package_by_id(application_id)
        
        session = InstallationSession(
            installation_id=session_id,
            application_id=application_id,
            current_step="Request Received",
            status="pending",
            percentage=0,
            logs=[f"{self._get_timestamp()} Request Received for {app.name if app else application_id}"],
            estimated_time=app.estimated_install_time if app else "Unknown"
        )
        self.sessions[session_id] = session
        
        # Initialize retries
        retry_manager.initialize_session(session_id, max_retries=app.retry_limit if app else 3)
        
        # Start async installation loop
        asyncio.create_task(self._run_installation(session_id))
        
        return session_id

    async def _run_installation(self, session_id: str):
        session = self.sessions.get(session_id)
        if not session:
            return

        app = package_repo.get_package_by_id(session.application_id)
        app_name = app.name if app else "Application"

        # The 13 step pipeline
        steps = [
            ("Request Received", 5, f"Processing request for {app_name}"),
            ("User Validation", 10, lambda: ValidationService.validate_user("dummy_user")),
            ("Device Validation", 15, lambda: ValidationService.validate_device("dummy_device")),
            ("Battery Validation", 20, lambda: ValidationService.validate_battery(
                BatteryService.get_current_battery_level(), 
                app.minimum_battery_percentage if app else 30
            )),
            ("Disk Validation", 25, lambda: ValidationService.validate_disk_space(app.package_size if app else "0")),
            ("Dependency Validation", 35, lambda: ValidationService.validate_dependencies(app.dependencies if app else [])),
            ("Package Validation", 45, lambda: ValidationService.validate_package(session.application_id)),
            ("Download Package", 60, lambda: {"status": "success", "reason": f"Downloading {app_name} package..."}),
            ("Verify Checksum", 70, lambda: ValidationService.validate_checksum(session.application_id, app.checksum if app else "")),
            ("Installation", 85, lambda: {"status": "success", "reason": f"Installing {app_name}..."}),
            ("Post Installation Validation", 90, lambda: {"status": "success", "reason": "Validating installation..."}),
            ("Email Notification", 95, lambda: {"status": "success", "reason": "Sending email notifications..."}),
            ("Completed", 100, lambda: {"status": "success", "reason": f"Installation of {app_name} completed successfully"})
        ]

        # Simulate a random failure just to show the retry engine working
        simulate_failure_at_step = "Download Package"
        simulated_failure_triggered = False

        step_index = 0
        while step_index < len(steps):
            step_name, percentage, action = steps[step_index]
            
            # Artificial sleep to simulate work
            await asyncio.sleep(2)
            
            session.current_step = step_name
            session.percentage = percentage
            
            # Execute step logic
            if isinstance(action, str):
                self._log(session, action)
            else:
                try:
                    # SIMULATE FAILURE DEMONSTRATION
                    if step_name == simulate_failure_at_step and not simulated_failure_triggered:
                        simulated_failure_triggered = True
                        raise Exception("Connection timed out while fetching package.")

                    result = action()
                    if result.get("status") == "failed":
                        # Immediate unrecoverable failure (e.g. Battery below threshold)
                        self._log(session, f"Failed: {result.get('reason')}")
                        session.status = "failed"
                        EmailService.send_installation_failure(app_name, result.get("reason"))
                        return
                    else:
                        self._log(session, result.get("reason"))
                        
                except Exception as e:
                    # Auto Remediation Engine
                    raw_error = str(e)
                    current_retry = retry_manager.get_current_retry(session_id) + 1
                    
                    self._log(session, f"Attempt {current_retry} Failed: {raw_error}")
                    
                    if retry_manager.can_retry(session_id):
                        retry_manager.record_failure(session_id, raw_error)
                        
                        error_type = ErrorParser.parse(raw_error)
                        remediation_action = RemediationService.remediate(error_type)
                        
                        self._log(session, f"Applying Remediation: {remediation_action}")
                        await asyncio.sleep(1) # wait before retry
                        # Don't increment step_index, so it retries the same step
                        continue
                    else:
                        self._log(session, "Automatic remediation failed after 3 attempts. Please contact your administrator.")
                        session.status = "failed"
                        EmailService.send_installation_failure(app_name, raw_error)
                        
                        if app and app.notify_admin:
                            EmailService.send_admin_notification(
                                subject=f"Installation Failed: {app_name}",
                                message=f"Automatic remediation failed for session {session_id}. Error: {raw_error}"
                            )
                        return

            if step_name == "Email Notification" and app and app.email_notification:
                EmailService.send_installation_success(app_name)
                
            if step_name == "Completed":
                session.status = "completed"

            step_index += 1

    def get_status(self, session_id: str) -> InstallationStatusResponse:
        session = self.sessions.get(session_id)
        if not session:
            return InstallationStatusResponse(
                step="Unknown",
                status="failed",
                percentage=0,
                message="Session not found",
                logs=[],
                estimated_time=""
            )

        return InstallationStatusResponse(
            step=session.current_step,
            status=session.status,
            percentage=session.percentage,
            message=session.logs[-1] if session.logs else "",
            logs=session.logs,
            estimated_time=session.estimated_time
        )

installation_manager = InstallationManager()
