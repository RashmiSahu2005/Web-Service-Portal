import json
from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.llm_service import LLMService
from app.core.config import settings
# pyrefly: ignore [missing-import]
import redis

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def analyze_approval_intent(text: str) -> str:
    # Quick rule-based fallback for common responses to avoid LLM flakiness
    lower_text = text.strip().lower()
    first_lines = "\n".join(lower_text.split("\n")[:5])
    
    import re
    # Check rejection first so 'Rejected. Do not install' is never classified as approved
    rejected_patterns = [
        r"\brejected\b", r"\breject\b", r"\bdenied\b", r"\bdeny\b",
        r"\bno\b", r"\bnope\b", r"\bstop\b", r"\bcancel\b",
        r"\bdo\s+not\s+install\b", r"\bdon'?t\s+install\b",
        r"\bdo\s+not\s+proceed\b", r"\bdon'?t\s+proceed\b",
    ]
    for pattern in rejected_patterns:
        if re.search(pattern, first_lines):
            logger.info("[EmailGraph] Rule-based classification: REJECTED")
            return "REJECTED"

    approved_patterns = [
        r"\bapproved?\b", r"\bapprov[ed]*\b",
        r"\byes\b", r"\byeah\b", r"\byep\b", r"\byup\b",
        r"\bgo\s+ahead\b", r"\bproceed\b", r"\binstall\b",
        r"\bok\b", r"\bokay\b", r"\bsure\b", r"\bfine\b", r"\bagreed\b"
    ]
    for pattern in approved_patterns:
        if re.search(pattern, first_lines):
            logger.info("[EmailGraph] Rule-based classification: APPROVED")
            return "APPROVED"

    prompt = f"""You are an intelligent email parsing agent. Analyze the following email reply and determine if the user is approving an installation request, rejecting it, or neither.
Many users simply reply "install", "yes", "go ahead", or "approved" to approve.
They might reply "no", "stop", "reject" to reject.

CRITICAL INSTRUCTION: Ignore any quoted previous emails or attached blocks at the bottom of the text (e.g. text starting with "On [Date]... wrote:"). Focus solely on the user's actual reply at the top.

Email Reply Text:
"{text}"

Return ONLY a valid JSON object matching this schema:
{{
    "intent": "APPROVED" | "REJECTED" | "NEITHER"
}}
"""
    try:
        response_text = LLMService.generate(prompt, json_mode=True)
        import re
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?|```$', '', clean_text).strip()
            
        data = json.loads(clean_text)
        return data.get("intent", "NEITHER")
    except Exception as e:
        logger.error(f"[EmailGraph] Agent approval classification failed: {str(e)}. Raw output was: {response_text}")
        return "NEITHER"

def check_approval_gate(state: EmailState) -> EmailState:
    logger.info(f"[EmailGraph] Checking approval gate for: {state.get('message_id')}")
    
    # 1. If this is an original request that just got validated and NOT an approval reply:
    import re
    has_approval_keyword = bool(re.search(r'^\s*(approved|approve|approvd|aprove|yes|proceed|go ahead|reject|rejected|no)\b', state.get("body", "").strip(), re.IGNORECASE))
    
    # Check if it already has an Incident ID (meaning it's either a reply or our own auto-generated email)
    has_existing_incident = bool(re.search(r"INC-[A-Z0-9]+", state.get("subject", "") + " " + state.get("body", "")))
    
    if state.get("status") == "PENDING_APPROVAL" and not has_approval_keyword and not has_existing_incident:
        import email.utils
        import uuid
        from app.services.email_service import EmailService
        _, email_addr = email.utils.parseaddr(state.get("sender", ""))
        state["requester_email"] = email_addr if email_addr else state.get("sender")
        
        # Generate an Incident ID to map this request
        incident_id = "INC-" + str(uuid.uuid4()).split('-')[0].upper()
        state["incident_id"] = incident_id
        
        # Save state to Redis using the incident ID and message ID (expires in 30 days)
        redis_client.set(f"incident:{incident_id}", json.dumps(state), ex=86400 * 30)
        if state.get("message_id"):
            redis_client.set(f"email_request:{state['message_id']}", json.dumps(state), ex=86400 * 30)
        
        # Email the admin approval group with the Incident ID
        EmailService.send_initial_approval_request(
            application_name=state.get("application_name"),
            hostname=state.get("target_host_ip") or "unknown",
            original_requester_email=state["requester_email"],
            incident_id=incident_id
        )
        
        logger.info(f"[EmailGraph] Original request saved. Waiting for approval reply for incident {incident_id}.")
        # Halt here. We don't map to installation yet.
        return state
        
    # 2. If this is potentially a reply (status might be RECEIVED or INVALID from IntentClassifier)
    # We must check if it's replying to a tracked message.
    msg_id = state.get("message_id")
    in_reply_to = state.get("in_reply_to")
    references = state.get("references", [])
    
    thread_ids_to_check = []
    if in_reply_to: thread_ids_to_check.append(in_reply_to)
    thread_ids_to_check.extend(references)
    
    # Check for mid-flight UPDATE ApprovalRequest in Postgres
    from app.database.database import SessionLocal
    from app.database.repositories.approval_repository import approval_repo
    
    db = SessionLocal()
    try:
        pending_approvals = []
        for tid in thread_ids_to_check:
            if not tid: continue
            matches = approval_repo.get_pending_by_thread(db, tid)
            pending_approvals.extend(matches)
            
        body = state.get("body", "")
        import re
        approval_id_match = re.search(r"Approval ID:\s*([a-zA-Z0-9\-]+)", body)
        if approval_id_match:
            app_id = approval_id_match.group(1)
            req = approval_repo.get(db, app_id)
            if req and req.status == "PENDING" and req not in pending_approvals:
                pending_approvals.append(req)
                
        if pending_approvals:
            import email.utils
            _, reply_sender = email.utils.parseaddr(state.get("sender", ""))
            reply_sender = reply_sender.lower().strip() if reply_sender else ""

            # Authorized approvers: APPROVAL_REQUEST_EMAILS (who received the request).
            # Fall back to ADMIN_APPROVAL_EMAILS only if APPROVAL_REQUEST_EMAILS is not configured.
            authorized_approvers = [e.lower() for e in (settings.APPROVAL_REQUEST_EMAILS or settings.ADMIN_APPROVAL_EMAILS)]

            for req in pending_approvals:
                if req.approval_reason == "DOWNGRADE_REQUEST":
                    if reply_sender != req.original_requester_email.lower():
                        logger.warning(f"[EmailGraph] Ignoring downgrade approval from {reply_sender} - not the original requester.")
                        req.status = "REJECTED"
                        approval_repo.update(db, req)
                        return {**state, "status": "REJECTED", "error_message": "REQUESTER_NOT_AUTHORIZED"}
                else:
                    if reply_sender not in authorized_approvers:
                        logger.warning(f"[EmailGraph] Ignoring approval from {reply_sender} - not an authorized approver.")
                        req.status = "REJECTED"
                        approval_repo.update(db, req)
                        return {**state, "status": "REJECTED", "error_message": "REQUESTER_NOT_AUTHORIZED"}

            body = state.get("body", "")
            intent = analyze_approval_intent(body)
            
            # Check for version in body for downgrade request
            new_version = None
            if intent == "NEITHER" and any(req.approval_reason == "DOWNGRADE_REQUEST" for req in pending_approvals):
                import re
                version_match = re.search(r'([0-9]+\.[0-9]+(?:\.[0-9]+)*)', body)
                if version_match:
                    new_version = version_match.group(1)
                    intent = "APPROVED" # Treat as approved with a new version
            
            if intent == "APPROVED":
                logger.info("[EmailGraph] Mid-flight approval processed!")
                from app.tasks.installation_tasks import resume_approved_update
                from app.services.email_service import EmailService
                from datetime import datetime
                for req in pending_approvals:
                    # Guard: already transitioned by another concurrent worker
                    if req.status != "PENDING":
                        logger.info(f"[EmailGraph] ApprovalRequest {req.id} already {req.status} (concurrent). Classified as ALREADY_PROCESSED.")
                        return {**state, "status": "INVALID", "error_message": "ALREADY_PROCESSED"}
                    req.status = "APPROVED"
                    req.approved_by = reply_sender
                    req.approved_at = datetime.utcnow()
                    if new_version:
                        req.target_version = new_version
                    approval_repo.update(db, req)
                    resume_approved_update.delay(req.id)
                    # Notify admin mailbox via threaded reply
                    try:
                        EmailService.send_approval_notification_to_admin(
                            application_name=req.application,
                            hostname=req.hostname,
                            incident_id=req.job_id,
                            approved_by=reply_sender,
                            admin_message_id=req.admin_message_id or "",
                            intent="APPROVED"
                        )
                    except Exception as notify_err:
                        logger.warning(f"[EmailGraph] Admin notification failed (non-fatal): {notify_err}")
                return {**state, "status": "APPROVED", "error_message": "Mid-flight approval processed."}
            elif intent == "REJECTED":
                from app.services.email_service import EmailService
                for req in pending_approvals:
                    if req.status != "PENDING":
                        logger.info(f"[EmailGraph] ApprovalRequest {req.id} already {req.status} (concurrent). Classified as ALREADY_PROCESSED.")
                        return {**state, "status": "INVALID", "error_message": "ALREADY_PROCESSED"}
                    req.status = "REJECTED"
                    approval_repo.update(db, req)
                    try:
                        EmailService.send_approval_notification_to_admin(
                            application_name=req.application,
                            hostname=req.hostname,
                            incident_id=req.job_id,
                            approved_by=reply_sender,
                            admin_message_id=req.admin_message_id or "",
                            intent="REJECTED"
                        )
                    except Exception as notify_err:
                        logger.warning(f"[EmailGraph] Admin notification failed (non-fatal): {notify_err}")
                return {**state, "status": "REJECTED"}
            else:
                return {**state, "status": "INVALID", "error_message": "Agent could not confirm approval."}
    finally:
        db.close()

    original_state = None
    original_msg_id = None
    
    # New Incident ID logic: Extract INC- ID from subject or body
    incident_match = re.search(r"INC-[A-Z0-9]+", state.get("subject", "") + " " + state.get("body", ""))
    if incident_match:
        incident_id = incident_match.group(0)
        logger.info(f"[EmailGraph] Extracted Incident ID {incident_id} from reply.")
        data = redis_client.get(f"incident:{incident_id}")
        if data:
            original_state = json.loads(data)
            original_msg_id = incident_id
            
    # Legacy fallback: use thread ids and message_ids just in case there are old pending requests
    if not original_state:
        for tid in thread_ids_to_check:
            if not tid: continue
            data = redis_client.get(f"email_request:{tid}")
            if data:
                original_state = json.loads(data)
                original_msg_id = tid
                break
                
    if not original_state:
        # Fallback: Subject-based matching for legacy email clients
        import re
        def clean_email_subject(subj: str) -> str:
            cleaned = subj
            pattern = r'^(?:re|fwd|aw|antw|wg)(?:\[\d+\])?\s*:\s*'
            while re.match(pattern, cleaned, re.IGNORECASE):
                cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE)
            
            cleaned = cleaned.strip().lower()
            cleaned = re.sub(r'\s+', ' ', cleaned)
            cleaned = re.sub(r'\s*:\s*', ':', cleaned)
            return cleaned

        raw_subj = state.get("subject", "")
        clean_subject = clean_email_subject(raw_subj)
        if clean_subject:
            for key in redis_client.scan_iter("email_request:*"):
                data = redis_client.get(key)
                if data:
                    parsed_state = json.loads(data)
                    orig_subj_clean = clean_email_subject(parsed_state.get("subject", ""))
                    if orig_subj_clean == clean_subject and parsed_state.get("status") == "PENDING_APPROVAL":
                        original_state = parsed_state
                        original_msg_id = key.split("email_request:")[1]
                        logger.info(f"[EmailGraph] Found matching thread via subject fallback: {original_msg_id}")
                        break
            
    if not original_state:
        # Not a reply to a tracked installation request.
        if state.get("status") in ["RECEIVED", "INVALID"]:
            return {**state, "status": "INVALID", "error_message": "Not an installation request or approval reply."}
        return state
        
    # We found the original request!
    # Have we already processed it?
    if original_state.get("status") in ["APPROVED", "COMPLETED", "REJECTED"]:
        logger.info(f"[EmailGraph] Thread {original_msg_id} already processed (Status: {original_state.get('status')}). Ignoring duplicate.")
        return {**state, "status": "INVALID", "error_message": "Already processed."}
        
    body = state.get("body", "")
    
    intent = analyze_approval_intent(body)
    
    if intent == "REJECTED":
        logger.info(f"[EmailGraph] Request {original_msg_id} was REJECTED by Agent.")
        original_state["status"] = "REJECTED"
        if original_msg_id and original_msg_id.startswith("INC-"):
            redis_client.set(f"incident:{original_msg_id}", json.dumps(original_state))
        else:
            redis_client.set(f"email_request:{original_msg_id}", json.dumps(original_state))
        return {**state, "status": "REJECTED"}
        
    if intent == "APPROVED":
        import email.utils
        _, reply_sender_addr = email.utils.parseaddr(state.get("sender", ""))
        reply_sender_addr = reply_sender_addr.lower().strip() if reply_sender_addr else ""

        # Authorize the sender against the configured approver list
        authorized_approvers = [e.lower() for e in (settings.APPROVAL_REQUEST_EMAILS or settings.ADMIN_APPROVAL_EMAILS)]
        if authorized_approvers and reply_sender_addr not in authorized_approvers:
            logger.warning(f"[EmailGraph] Unauthorized approver {reply_sender_addr} on Redis incident {original_msg_id}. Ignoring.")
            return {**state, "status": "INVALID", "error_message": "UNAUTHORIZED_APPROVER"}

        logger.info(f"[EmailGraph] Request {original_msg_id} was APPROVED by {reply_sender_addr}!")
        original_state["status"] = "APPROVED"
        
        # Save back to Redis using whichever key type we used
        if original_msg_id and original_msg_id.startswith("INC-"):
            redis_client.set(f"incident:{original_msg_id}", json.dumps(original_state))
        else:
            redis_client.set(f"email_request:{original_msg_id}", json.dumps(original_state))
        
        # Merge the original extracted details into the current state so it can proceed to mapping
        return {
            **state,
            "status": "APPROVED",
            "applications": original_state.get("applications"),
            "application_name": original_state.get("application_name"),
            "application_id": original_state.get("application_id"),
            "version": original_state.get("version"),
            "target_host_ip": original_state.get("target_host_ip"),
            "host_id": original_state.get("host_id"),
            "requester_email": original_state.get("requester_email") or original_state.get("sender"),
        }
        
    logger.info(f"[EmailGraph] Reply on thread {original_msg_id} was classified as NEITHER.")
    return {**state, "status": "INVALID", "error_message": "Agent could not confirm approval or rejection."}
