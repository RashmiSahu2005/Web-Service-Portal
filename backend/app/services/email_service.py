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
        original_message_id: str,
        approval_id: str
    ):
        recipient_emails = settings.ADMIN_APPROVAL_EMAILS
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
DeployIQ Update Approval - Approval ID: {approval_id}

To approve:
Reply APPROVED in this email thread.

No update will be performed unless an approval is received.
"""

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = ", ".join(recipient_emails)
        msg['Subject'] = subject
        
        import email.utils
        admin_message_id = email.utils.make_msgid(domain="deployiq.local")
        msg['Message-ID'] = admin_message_id

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
            server.sendmail(settings.SMTP_SENDER_EMAIL, recipient_emails, msg.as_string())
            server.quit()
            logger.info("EmailService: Approval Email Sent")
            return (True, admin_message_id)
        except Exception as e:
            logger.error(f"EmailService: Approval Email Failed: {e}")
            return (False, str(e))

    @staticmethod
    def send_user_downgrade_request(
        application_name: str,
        current_version: str,
        target_version: str,
        recipient_email: str,
        original_message_id: str,
        approval_id: str
    ):
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping user downgrade email.")
            return True, "SMTP disabled"

        subject = f"ACTION REQUIRED: Clarification needed for DeployIQ Update - {application_name}"
        
        body = f"""DeployIQ detected that the requested update would result in a downgrade.

Current version: {current_version}
Target/discovered version: {target_version}

No changes were made.

If you want this version installed, reply APPROVE to this email.
If you want a different version, reply with the exact version you want installed.

DeployIQ Update Approval - Approval ID: {approval_id}
"""

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        import email.utils
        admin_message_id = email.utils.make_msgid(domain="deployiq.local")
        msg['Message-ID'] = admin_message_id

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
            logger.info("EmailService: Downgrade User Clarification Email Sent")
            return (True, admin_message_id)
        except Exception as e:
            logger.error(f"EmailService: Downgrade User Clarification Email Failed: {e}")
            return (False, str(e))

    @staticmethod
    def send_version_detection_failed_email(
        recipient_email: str,
        application_name: str,
        hostname: str,
        reason: str = "",
        in_reply_to: str = None
    ):
        """
        Sent when an UPDATE request is blocked because the installed version
        could not be reliably determined on the target host.
        """
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping version-detection-failed email.")
            return True, "SMTP disabled"

        subject = f"DeployIQ - Update Blocked: Could Not Detect Installed Version of {application_name}"

        body = (
            f"Your requested update for {application_name} on host {hostname} has been blocked.\n\n"
            f"Reason: DeployIQ could not reliably determine the currently installed version on this host.\n\n"
            f"Technical details:\n{reason}\n\n"
            f"Status: UPDATE BLOCKED — VERSION_DETECTION_FAILED\n\n"
            f"What to do:\n"
            f"  1. Verify that {application_name} is accessible from the host's non-interactive shell.\n"
            f"  2. Ensure the binary is in a standard path (e.g. /usr/bin/, /usr/local/bin/).\n"
            f"  3. Re-submit the update request after confirming the application is properly installed.\n"
        )

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to

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
            logger.info("EmailService: Version Detection Failed Email Sent")
            return (True, "sent")
        except Exception as e:
            logger.error(f"EmailService: Version Detection Failed Email Failed: {e}")
            return (False, str(e))

    @staticmethod
    def send_update_blocked_email(
        recipient_email: str,
        application_name: str,
        hostname: str,
        in_reply_to: str = None
    ):
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping update blocked email.")
            return True, "SMTP disabled"

        subject = f"DeployIQ - Update Blocked: {application_name}"
        
        body = (
            f"Your requested update cannot be performed because {application_name} is not installed on host {hostname}.\n\n"
            f"Please submit an installation request for this application and approve it in the mail thread.\n\n"
            f"Status: UPDATE BLOCKED - APPLICATION NOT INSTALLED\n"
        )

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to

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
            logger.info("EmailService: Update Blocked Email Sent")
            return (True, "sent")
        except Exception as e:
            logger.error(f"EmailService: Update Blocked Email Failed: {e}")
            return (False, str(e))

    @staticmethod
    def send_version_discovery_failed_email(
        recipient_email: str,
        application_name: str,
        hostname: str,
        installed_version: str,
        reason: str = "",
        in_reply_to: str = None
    ):
        """
        Sent when an UPDATE request is blocked because authoritative version discovery
        could not reliably establish a trustworthy newer version.
        """
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping version discovery failed email.")
            return True, "SMTP disabled"

        subject = f"DeployIQ - Update Blocked: Version Discovery Failed for {application_name}"
        body = (
            f"Your requested update for {application_name} on host {hostname} could not be completed.\n\n"
            f"Currently installed version: {installed_version}\n"
            f"Status: UPDATE BLOCKED — VERSION_DISCOVERY_FAILED\n\n"
            f"Reason: {reason or 'DeployIQ could not establish a trustworthy newer version from authoritative vendor/package repositories.'}\n\n"
            f"To protect system stability, updates are not performed when target versions cannot be authoritatively verified.\n"
        )

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to

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
            logger.info("EmailService: Version Discovery Failed Email Sent")
            return (True, "sent")
        except Exception as e:
            logger.error(f"EmailService: Version Discovery Failed Email Failed: {e}")
            return (False, str(e))

    @staticmethod
    def send_host_not_found_email(
        recipient_email: str,
        requested_host: str,
        in_reply_to: str = None
    ):
        """
        Sent to the original requester when the requested host was not found in FleetDM.
        """
        if not settings.SMTP_ENABLED:
            logger.info("SMTP disabled, skipping host not found email.")
            return True, "SMTP disabled"

        if not recipient_email or "@" not in recipient_email:
            logger.warning(f"Invalid recipient email '{recipient_email}', skipping host not found email.")
            return False, "Invalid recipient email"

        subject = f"DeployIQ - Host Not Found in FleetDM ({requested_host})"
        body = (
            f"Hello,\n\n"
            f"The requested host {requested_host} was not found in FleetDM. "
            f"No installation/update was performed. "
            f"Please contact the administrator/team responsible for FleetDM and verify that the host is enrolled.\n\n"
            f"Thank you,\nDeployIQ\n"
        )

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to

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
            logger.info(f"EmailService: Host Not Found email sent to {recipient_email}")
            return (True, "sent")
        except Exception as e:
            logger.error(f"EmailService: Host Not Found email failed: {e}")
            return (False, str(e))
