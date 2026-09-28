import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.logger import logger
from app.core.config import settings
import traceback

class EmailService:
    @staticmethod
    def send_installation_success(
        recipient_email: str,
        application_name: str,
        status: str,
        timestamp: str,
        hostname: str = None
    ):
        if not settings.SMTP_ENABLED:
            msg = "SMTP is disabled in configuration. Skipping email."
            logger.info(f"EmailService: {msg}")
            return (True, msg)

        subject = "DeployIQ - Installation Successful"
        
        body = f"""Hello,

Your requested application has been installed successfully.

Application :
{application_name}

Status :
{status}

Installation Time :
{timestamp}
"""
        if hostname:
            body += f"\nHostname :\n{hostname}\n"

        body += """
Thank you,

DeployIQ"""

        logger.info(f"EmailService: Email Triggered for {application_name} to {recipient_email}")
        
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            # Try starttls, but ignore if the server doesn't support it (e.g. mock servers)
            try:
                server.starttls()
            except Exception:
                pass
                
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
            server.sendmail(settings.SMTP_SENDER_EMAIL, [recipient_email], msg.as_string())
            server.quit()
            logger.info("EmailService: Email Sent Successfully")
            return (True, "Email Sent Successfully")
        except Exception as e:
            logger.error(f"EmailService: Email Failed to send. Error: {e}")
            logger.debug(traceback.format_exc())
            return (False, f"Email Failed to send. Error: {e}")

    @staticmethod
    def send_installation_failure(
        recipient_email: str,
        application_name: str,
        status: str,
        timestamp: str,
        reason: str,
        hostname: str = None
    ):
        if not settings.SMTP_ENABLED:
            msg = "SMTP is disabled in configuration. Skipping email."
            logger.info(f"EmailService: {msg}")
            return (True, msg)

        subject = "DeployIQ - Installation Failed"
        
        body = f"""Hello,

Your requested application installation has failed.

Application :
{application_name}

Status :
{status}

Failure Reason :
{reason}

Installation Time :
{timestamp}
"""
        if hostname:
            body += f"\nHostname :\n{hostname}\n"

        body += """
Thank you,

DeployIQ"""

        logger.info(f"EmailService: Failure Email Triggered for {application_name} to {recipient_email}")
        
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            try:
                server.starttls()
            except Exception:
                pass
                
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
            server.sendmail(settings.SMTP_SENDER_EMAIL, [recipient_email], msg.as_string())
            server.quit()
            logger.info("EmailService: Failure Email Sent Successfully")
            return (True, "Failure Email Sent Successfully")
        except Exception as e:
            logger.error(f"EmailService: Failure Email Failed to send. Error: {e}")
            logger.debug(traceback.format_exc())
            return (False, f"Failure Email Failed to send. Error: {e}")

    @staticmethod
    def send_multi_app_report(
        recipient_email: str,
        summary_text: str,
        overall_status: str,
        timestamp: str,
        hostname: str = None
    ):
        if not settings.SMTP_ENABLED:
            msg = "SMTP is disabled in configuration. Skipping email."
            logger.info(f"EmailService: {msg}")
            return (True, msg)

        subject = f"DeployIQ - Installation Request: {overall_status}"
        
        body = f"""Hello,

Your installation request has completed with status: {overall_status}

Details:
{summary_text}

Installation Time :
{timestamp}
"""
        if hostname:
            body += f"\nHostname :\n{hostname}\n"

        body += """
Thank you,

DeployIQ"""

        logger.info(f"EmailService: Multi-App Email Triggered to {recipient_email}")
        
        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            try:
                server.starttls()
            except Exception:
                pass
                
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
            server.sendmail(settings.SMTP_SENDER_EMAIL, [recipient_email], msg.as_string())
            server.quit()
            logger.info("EmailService: Multi-App Report Email Sent Successfully")
            return (True, "Email Sent Successfully")
        except Exception as e:
            logger.error(f"EmailService: Multi-App Report Email Failed to send. Error: {e}")
            logger.debug(traceback.format_exc())
            return (False, f"Multi-App Report Email Failed to send. Error: {e}")

    @staticmethod
    def send_admin_approval_request(
        application_name: str,
        hostname: str,
        current_version: str,
        target_version: str,
        approval_reason: str,
        planned_action: str,
        risk: str,
        original_requester_email: str,
        original_message_id: str
    ):
        recipient_email = settings.UPDATE_APPROVAL_ADMIN_EMAIL
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping approval email.")
            return True, "SMTP disabled"

        subject = f"ACTION REQUIRED: Approval for DeployIQ Update - {application_name} on {hostname}"
        
        body = f"""DeployIQ requires administrative approval before updating {application_name} on host {hostname}.

Current version: {current_version}
Target version: {target_version}

Reason approval is required:
{approval_reason}

Planned action:
{planned_action}

Risk:
{risk}

Original requester: {original_requester_email}

To approve:
Reply APPROVED in this email thread.

No update will be performed unless an approval is received.
"""

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        if original_message_id:
            msg['In-Reply-To'] = original_message_id
            msg['References'] = original_message_id

        msg.attach(MIMEText(body, 'plain'))
        
        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            try:
                server.starttls()
            except Exception:
                pass
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_SENDER_EMAIL, [recipient_email], msg.as_string())
            server.quit()
            logger.info("EmailService: Approval Email Sent")
            return (True, "Email Sent")
        except Exception as e:
            logger.error(f"EmailService: Approval Email Failed: {e}")
            return (False, str(e))
