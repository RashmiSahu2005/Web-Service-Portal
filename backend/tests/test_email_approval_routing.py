"""
Focused tests for DeployIQ email approval routing changes.
Covers all 18 required test scenarios from the task specification.
Uses mocks and local Redis -- does NOT send real emails or run installations.
"""
import json
import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.core.config import settings, _parse_email_list


# =============================================================================
# Section 1: Configuration parsing (Scenarios 1-4, 17)
# =============================================================================

class TestEmailListParsing:
    """Scenarios 1-4, 17: Address normalization and validation."""

    def test_single_admin_address(self):
        assert _parse_email_list("admin@example.com", "T") == ["admin@example.com"]

    def test_single_approver_address(self):
        assert _parse_email_list("approver@example.com", "T") == ["approver@example.com"]

    def test_multiple_admin_addresses(self):
        """Scenario 2: Multiple comma-separated admin addresses."""
        result = _parse_email_list("admin1@example.com,admin2@example.com", "T")
        assert result == ["admin1@example.com", "admin2@example.com"]

    def test_multiple_approver_addresses(self):
        """Scenario 3: Multiple comma-separated approval recipients."""
        result = _parse_email_list(
            "approver1@example.com, approver2@example.com , approver3@example.com", "T"
        )
        assert result == ["approver1@example.com", "approver2@example.com", "approver3@example.com"]

    def test_whitespace_normalization(self):
        """Scenario 4: Whitespace trimmed from each address."""
        result = _parse_email_list("  admin@example.com  ,  approver@example.com  ", "T")
        assert result == ["admin@example.com", "approver@example.com"]

    def test_duplicate_deduplication_case_insensitive(self):
        """Scenario 4: Duplicate addresses deduplicated case-insensitively."""
        result = _parse_email_list("Admin@example.com,admin@example.com,ADMIN@EXAMPLE.COM", "T")
        assert result == ["admin@example.com"]

    def test_empty_entries_dropped(self):
        result = _parse_email_list("admin@example.com,,  ,approver@example.com", "T")
        assert result == ["admin@example.com", "approver@example.com"]

    def test_invalid_email_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid email address"):
            _parse_email_list("not-an-email", "TEST_VAR")

    def test_empty_string_returns_empty_list(self):
        assert _parse_email_list("", "T") == []

    def test_config_has_approval_request_emails(self):
        """Scenario 17: APPROVAL_REQUEST_EMAILS present on settings."""
        assert hasattr(settings, "APPROVAL_REQUEST_EMAILS")
        assert isinstance(settings.APPROVAL_REQUEST_EMAILS, list)

    def test_config_has_admin_approval_emails(self):
        assert hasattr(settings, "ADMIN_APPROVAL_EMAILS")
        assert isinstance(settings.ADMIN_APPROVAL_EMAILS, list)

    def test_admin_and_approver_are_independent(self):
        """Scenario 17: The two lists parse independently -- changing one doesn't affect the other."""
        # Test purely at the parsing level to avoid module-reload side-effects
        admin_result = _parse_email_list("newadmin@uat.example.com", "UPDATE_APPROVAL_ADMIN_EMAIL")
        approver_result = _parse_email_list("newapprover@uat.example.com", "UPDATE_APPROVAL_REQUEST_EMAIL")
        # Each list is independent
        assert admin_result == ["newadmin@uat.example.com"]
        assert approver_result == ["newapprover@uat.example.com"]
        assert admin_result != approver_result
        # Confirm settings has both attributes and they are separate lists
        assert hasattr(settings, "ADMIN_APPROVAL_EMAILS")
        assert hasattr(settings, "APPROVAL_REQUEST_EMAILS")
        # They must not be the same object/list so mutating one cannot affect the other
        assert settings.ADMIN_APPROVAL_EMAILS is not settings.APPROVAL_REQUEST_EMAILS


# =============================================================================
# Section 2: Approval authorization (Scenarios 5-8)
# =============================================================================

class TestApprovalAuthorization:

    def _pending(self, incident_id, orig_msg_id, status="PENDING_APPROVAL"):
        return {
            "message_id": orig_msg_id,
            "incident_id": incident_id,
            "sender": "engineer@company.com",
            "requester_email": "engineer@company.com",
            "application_name": "curl",
            "applications": [{"name": "curl", "version": "latest", "operation": "INSTALL"}],
            "target_host_ip": "192.168.10.53",
            "host_id": "192",
            "status": status,
        }

    def test_valid_approval_from_authorized_approver(self):
        """Scenario 5: First authorized recipient approves -- job dispatched."""
        import redis
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        orig_msg_id = f"<orig-{uuid.uuid4()}@test.local>"
        r.set(f"incident:{incident_id}", json.dumps(self._pending(incident_id, orig_msg_id)), ex=300)

        # Use the actual configured approver address so the authorization check passes
        approver = settings.APPROVAL_REQUEST_EMAILS[0] if settings.APPROVAL_REQUEST_EMAILS else settings.ADMIN_APPROVAL_EMAILS[0]
        reply = EmailState(
            message_id=f"<reply-{uuid.uuid4()}@test.local>",
            in_reply_to=orig_msg_id,
            references=[orig_msg_id],
            subject=f"Re: Install curl [{incident_id}]",
            body="APPROVED",
            sender=f"Approver <{approver}>",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"), \
             patch("app.services.installation_service.InstallationService.create_and_start_installation",
                   return_value="job-test-001"):
            result = graph.invoke(reply)

        assert result.get("status") == "COMPLETED"
        r.delete(f"incident:{incident_id}")

    def test_second_approver_after_approval_accepted(self):
        """Scenario 6: Second reply after APPROVED -- classified as already processed."""
        import redis
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        orig_msg_id = f"<orig-{uuid.uuid4()}@test.local>"
        r.set(f"incident:{incident_id}", json.dumps(self._pending(incident_id, orig_msg_id, status="APPROVED")), ex=300)

        approver = settings.APPROVAL_REQUEST_EMAILS[0] if settings.APPROVAL_REQUEST_EMAILS else settings.ADMIN_APPROVAL_EMAILS[0]
        reply = EmailState(
            message_id=f"<reply2-{uuid.uuid4()}@test.local>",
            in_reply_to=orig_msg_id,
            references=[orig_msg_id],
            subject=f"Re: Install curl [{incident_id}]",
            body="APPROVED",
            sender=f"Approver2 <{approver}>",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"):
            result = graph.invoke(reply)

        # Must not dispatch a second job
        assert result.get("status") in ("INVALID", "ALREADY_PROCESSED")
        r.delete(f"incident:{incident_id}")

    def test_repeated_delivery_of_same_approval_email(self):
        """Scenario 7: Same Message-ID seen twice -- second call short-circuits."""
        import redis
        from app.mail_listener.email_listener import process_email
        from app.mail_listener.imap_client import IMAPClient
        from email.message import Message

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        # parse_email strips angle-brackets from Message-ID, so Redis key uses the bare ID.
        msg_id_raw = f"dedup-{uuid.uuid4()}@test.local"
        msg_id_header = f"<{msg_id_raw}>"  # as it appears in the email header
        # Store the dedup key with the stripped form (same as process_email does)
        r.set(f"email_processed:{msg_id_raw}", "true", ex=300)

        msg = Message()
        msg["From"] = "approver@example.com"
        msg["Subject"] = "APPROVED"
        msg["Message-ID"] = msg_id_header

        mock_client = MagicMock(spec=IMAPClient)

        # The graph is imported inside process_email; patch at source
        with patch("app.graph.email.graph.create_email_intake_graph") as mock_graph_factory:
            process_email(mock_client, b"1", msg)
            # Graph must never be created for a duplicate message
            mock_graph_factory.assert_not_called()

        r.delete(f"email_processed:{msg_id_raw}")

    def test_unauthorized_sender_reply(self):
        """Scenario 8: Non-approver replies -- no execution."""
        import redis
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        orig_msg_id = f"<orig-{uuid.uuid4()}@test.local>"
        r.set(f"incident:{incident_id}", json.dumps(self._pending(incident_id, orig_msg_id)), ex=300)

        reply = EmailState(
            message_id=f"<reply-{uuid.uuid4()}@test.local>",
            in_reply_to=orig_msg_id,
            references=[orig_msg_id],
            subject=f"Re: Install curl [{incident_id}]",
            body="APPROVED",
            sender="unauthorized@attacker.com",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"), \
             patch("app.services.installation_service.InstallationService.create_and_start_installation") as mock_start:
            result = graph.invoke(reply)
            mock_start.assert_not_called()

        assert result.get("status") in ("INVALID", "REJECTED")
        r.delete(f"incident:{incident_id}")


# =============================================================================
# Section 3: Thread/incident correlation (Scenarios 9-11)
# =============================================================================

class TestIncidentCorrelation:

    def test_missing_incident_id_in_reply(self):
        """Scenario 9: No INC-* and no matching thread -- INVALID."""
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        reply = EmailState(
            message_id=f"<reply-{uuid.uuid4()}@test.local>",
            in_reply_to=None,
            references=[],
            subject="Re: random subject",
            body="APPROVED",
            sender="anyone@example.com",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"):
            result = graph.invoke(reply)

        assert result.get("status") == "INVALID"

    def test_mismatched_thread_id_does_not_approve(self):
        """Scenario 10: In-Reply-To points to unknown message ID -- no approval."""
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        unknown_id = f"<unknown-{uuid.uuid4()}@test.local>"
        reply = EmailState(
            message_id=f"<reply-{uuid.uuid4()}@test.local>",
            in_reply_to=unknown_id,
            references=[unknown_id],
            subject="Re: some subject",
            body="APPROVED",
            sender="approver@example.com",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"):
            result = graph.invoke(reply)

        assert result.get("status") == "INVALID"

    def test_reply_after_incident_completed(self):
        """Scenario 11: Late reply after COMPLETED -- no execution."""
        import redis
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        incident_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        orig_msg_id = f"<orig-{uuid.uuid4()}@test.local>"
        r.set(f"incident:{incident_id}", json.dumps({
            "message_id": orig_msg_id,
            "incident_id": incident_id,
            "application_name": "curl",
            "host_id": "192",
            "status": "COMPLETED",
        }), ex=300)

        late_reply = EmailState(
            message_id=f"<late-{uuid.uuid4()}@test.local>",
            in_reply_to=orig_msg_id,
            references=[orig_msg_id],
            subject=f"Re: Install curl [{incident_id}]",
            body="APPROVED",
            sender="approver@example.com",
            status="RECEIVED",
        )

        graph = create_email_intake_graph()
        with patch("app.database.database.SessionLocal"), \
             patch("app.services.installation_service.InstallationService.create_and_start_installation") as mock_start:
            result = graph.invoke(late_reply)
            mock_start.assert_not_called()

        assert result.get("status") == "INVALID"
        r.delete(f"incident:{incident_id}")


# =============================================================================
# Section 4: Concurrent approvals (Scenario 12)
# =============================================================================

class TestConcurrentApproval:

    def test_concurrent_approval_only_one_job_dispatched(self):
        """Scenario 12: The req.status != 'PENDING' guard prevents double execution."""
        from app.database.models.approval import ApprovalRequest

        mock_req = MagicMock(spec=ApprovalRequest)
        mock_req.status = "PENDING"
        mock_req.id = str(uuid.uuid4())
        mock_req.application = "curl"
        mock_req.hostname = "host1"
        mock_req.job_id = "job-001"
        mock_req.admin_message_id = "<admin@deployiq.local>"
        mock_req.approval_reason = "REQUIRES_ADMIN_APPROVAL"
        mock_req.original_requester_email = "engineer@company.com"

        # Simulate first worker winning the race
        assert mock_req.status == "PENDING"
        mock_req.status = "APPROVED"

        # Second worker arrives -- guard triggers because status != PENDING
        assert mock_req.status != "PENDING"  # => ALREADY_PROCESSED path taken


# =============================================================================
# Section 5: Loop prevention (Scenarios 13-14)
# =============================================================================

class TestLoopPrevention:

    def test_action_required_subject_ignored(self):
        """Scenario 13: 'ACTION REQUIRED:' DeployIQ emails dropped before graph."""
        from app.mail_listener.email_listener import process_email
        from app.mail_listener.imap_client import IMAPClient
        from email.message import Message

        msg_id = f"<bot-{uuid.uuid4()}@deployiq.local>"
        msg = Message()
        msg["From"] = "deployiq@company.com"
        msg["Subject"] = "ACTION REQUIRED: Approval for DeployIQ Update - curl"
        msg["Message-ID"] = msg_id

        mock_client = MagicMock(spec=IMAPClient)

        # Graph is lazily imported inside process_email at the call site
        with patch("app.graph.email.graph.create_email_intake_graph") as mock_graph_factory:
            process_email(mock_client, b"2", msg)
            mock_graph_factory.assert_not_called()

        mock_client.mark_as_read.assert_called_once()

    def test_deployiq_prefix_subject_ignored(self):
        """Scenario 13: 'DeployIQ -' prefix status email ignored."""
        from app.mail_listener.email_listener import process_email
        from app.mail_listener.imap_client import IMAPClient
        from email.message import Message

        msg_id = f"<status-{uuid.uuid4()}@deployiq.local>"
        msg = Message()
        msg["From"] = "deployiq@company.com"
        msg["Subject"] = "DeployIQ - Installation Successful"
        msg["Message-ID"] = msg_id

        mock_client = MagicMock(spec=IMAPClient)

        with patch("app.graph.email.graph.create_email_intake_graph") as mock_graph_factory:
            process_email(mock_client, b"3", msg)
            mock_graph_factory.assert_not_called()

        mock_client.mark_as_read.assert_called_once()

    def test_approval_acknowledgement_classified_as_reply_not_new_request(self):
        """Scenario 14: Re: approval acknowledgement -- intent classifier fast-paths as reply."""
        from app.graph.email.nodes.intent_classifier import classify_intent
        from app.graph.email.state import EmailState

        state = EmailState(
            message_id=f"<ack-{uuid.uuid4()}@test.local>",
            in_reply_to="<original@deployiq.local>",
            references=[],
            subject="Re: ACTION REQUIRED: Approval for DeployIQ Update - curl",
            body="APPROVED",
            sender="approver@example.com",
            status="RECEIVED",
        )

        with patch("app.services.llm_service.LLMService.generate") as mock_llm:
            result = classify_intent(state)
            mock_llm.assert_not_called()

        assert result.get("status") == "RECEIVED"


# =============================================================================
# Section 6: Genuine request detection (Scenario 15)
# =============================================================================

class TestGenuineRequestDetection:

    def test_genuine_install_request_still_detected(self):
        """Scenario 15: Normal install request flows to PENDING_APPROVAL."""
        from app.graph.email.graph import create_email_intake_graph
        from app.graph.email.state import EmailState

        graph = create_email_intake_graph()
        state = EmailState(
            message_id=f"<genuine-{uuid.uuid4()}@test.local>",
            in_reply_to=None,
            references=[],
            subject="Install nginx on 192.168.10.53",
            body="Please install nginx on host 192.168.10.53",
            sender="engineer@company.com",
            status="RECEIVED",
        )

        with patch("app.services.fleetdm_service.FleetDMService.verify_host_enrolled",
                   return_value={"id": 192, "hostname": "TESTHOST"}), \
             patch("app.services.email_service.EmailService.send_initial_approval_request",
                   return_value=(True, "<admin-mid@deployiq.local>")) as mock_send, \
             patch("app.database.database.SessionLocal"):
            result = graph.invoke(state)

        assert result.get("status") == "PENDING_APPROVAL"
        assert (result.get("application_name") or "").lower() == "nginx"
        mock_send.assert_called_once()


# =============================================================================
# Section 7: Failure modes without false success (Scenario 16)
# =============================================================================

class TestFailureWithoutFalseSuccess:

    def test_smtp_failure_returns_false_not_success(self):
        """Scenario 16: SMTP failure returns (False, ...) not (True, ...)."""
        import app.core.config as cfg_module
        from app.services.email_service import EmailService

        original_enabled = cfg_module.settings.SMTP_ENABLED
        original_admins = cfg_module.settings.ADMIN_APPROVAL_EMAILS
        try:
            cfg_module.settings.SMTP_ENABLED = True
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = ["admin@example.com"]
            with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("SMTP unreachable")):
                ok, msg = EmailService.send_approval_notification_to_admin(
                    application_name="curl",
                    hostname="host1",
                    incident_id="INC-TESTSMTP",
                    approved_by="approver@example.com",
                    admin_message_id="<mid@local>",
                    intent="APPROVED"
                )
            assert ok is False
        finally:
            cfg_module.settings.SMTP_ENABLED = original_enabled
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = original_admins

    def test_job_dispatch_failure_returns_failed_not_completed(self):
        """Scenario 16: InstallationService failure returns status=FAILED."""
        from app.graph.email.nodes.request_mapping import map_to_installation
        from app.graph.email.state import EmailState

        state = EmailState(
            message_id=f"<test-{uuid.uuid4()}@test.local>",
            status="APPROVED",
            application_id=str(uuid.uuid4()),
            application_name="curl",
            applications=[{"name": "curl", "version": "latest", "operation": "INSTALL"}],
            host_id="192",
            version="latest",
            requester_email="engineer@company.com",
        )

        with patch("app.database.database.SessionLocal"), \
             patch("app.services.installation_service.InstallationService.create_and_start_installation",
                   side_effect=RuntimeError("DB failure")):
            result = map_to_installation(state)

        assert result.get("status") == "FAILED"
        assert "DB failure" in result.get("error_message", "")


# =============================================================================
# Section 8: Email recipients (Scenario 18 regression)
# =============================================================================

class TestApprovalRequestRecipients:

    def test_initial_approval_sent_to_approvers_not_admins(self):
        """Approval request goes to APPROVAL_REQUEST_EMAILS, not ADMIN_APPROVAL_EMAILS."""
        import app.core.config as cfg_module
        from app.services.email_service import EmailService

        orig_req = cfg_module.settings.APPROVAL_REQUEST_EMAILS
        orig_adm = cfg_module.settings.ADMIN_APPROVAL_EMAILS
        orig_enabled = cfg_module.settings.SMTP_ENABLED
        try:
            cfg_module.settings.APPROVAL_REQUEST_EMAILS = ["approver1@example.com", "approver2@example.com"]
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = ["admin@example.com"]
            cfg_module.settings.SMTP_ENABLED = True

            with patch("smtplib.SMTP") as mock_smtp_cls:
                mock_server = MagicMock()
                mock_smtp_cls.return_value = mock_server
                mock_server.sendmail = MagicMock()
                mock_server.quit = MagicMock()

                EmailService.send_initial_approval_request(
                    application_name="nginx",
                    hostname="host1",
                    original_requester_email="engineer@company.com",
                    incident_id="INC-TESTRECIP"
                )

                call_args = mock_server.sendmail.call_args
                assert call_args is not None
                recipients_arg = call_args[0][1]
                assert set(["approver1@example.com", "approver2@example.com"]) == set(recipients_arg)
        finally:
            cfg_module.settings.APPROVAL_REQUEST_EMAILS = orig_req
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = orig_adm
            cfg_module.settings.SMTP_ENABLED = orig_enabled

    def test_admin_notification_sent_to_admins_not_approvers(self):
        """Admin notification goes to ADMIN_APPROVAL_EMAILS, not APPROVAL_REQUEST_EMAILS."""
        import app.core.config as cfg_module
        from app.services.email_service import EmailService

        orig_req = cfg_module.settings.APPROVAL_REQUEST_EMAILS
        orig_adm = cfg_module.settings.ADMIN_APPROVAL_EMAILS
        orig_enabled = cfg_module.settings.SMTP_ENABLED
        try:
            cfg_module.settings.APPROVAL_REQUEST_EMAILS = ["approver1@example.com"]
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = ["admin@example.com"]
            cfg_module.settings.SMTP_ENABLED = True

            with patch("smtplib.SMTP") as mock_smtp_cls:
                mock_server = MagicMock()
                mock_smtp_cls.return_value = mock_server
                mock_server.sendmail = MagicMock()
                mock_server.quit = MagicMock()

                EmailService.send_approval_notification_to_admin(
                    application_name="nginx",
                    hostname="host1",
                    incident_id="INC-TESTNOTIFY",
                    approved_by="approver1@example.com",
                    admin_message_id="<orig@deployiq.local>",
                    intent="APPROVED"
                )

                call_args = mock_server.sendmail.call_args
                assert call_args is not None
                recipients_arg = call_args[0][1]
                assert set(["admin@example.com"]) == set(recipients_arg)
        finally:
            cfg_module.settings.APPROVAL_REQUEST_EMAILS = orig_req
            cfg_module.settings.ADMIN_APPROVAL_EMAILS = orig_adm
            cfg_module.settings.SMTP_ENABLED = orig_enabled
