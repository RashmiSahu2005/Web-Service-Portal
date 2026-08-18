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

        subject = "Application Hub - Installation Successful"
        
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

Application Hub"""

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

        subject = "Application Hub - Installation Failed"
        
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

Application Hub"""

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
