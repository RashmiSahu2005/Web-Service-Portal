from app.core.logger import logger

class EmailService:
    @staticmethod
    def send_installation_success(application_name: str, user_email: str = "user@example.com", cc: str = None, attachments: list = None):
        logger.info(f"EmailService: Sending SUCCESS email for {application_name} to {user_email}")
        if cc:
            logger.info(f"EmailService: CC'ing {cc}")
        if attachments:
            logger.info(f"EmailService: Including {len(attachments)} attachments")
        
    @staticmethod
    def send_installation_failure(application_name: str, reason: str, user_email: str = "user@example.com", cc: str = None, attachments: list = None):
        logger.error(f"EmailService: Sending FAILURE email for {application_name} to {user_email}. Reason: {reason}")
        if cc:
            logger.error(f"EmailService: CC'ing {cc}")
        if attachments:
            logger.error(f"EmailService: Including {len(attachments)} attachments")

    @staticmethod
    def send_admin_notification(subject: str, message: str, admin_email: str = "admin@example.com"):
        logger.warning(f"EmailService: Sending ADMIN notification to {admin_email}. Subject: {subject} - Message: {message}")
