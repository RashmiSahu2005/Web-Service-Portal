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
    
    approved_words = [
        "approved", "approve", "approvd", "aprove", "aproved",
        "yes", "yeah", "yep", "yup",
        "go ahead", "proceed", "install", 
        "ok", "okay", "sure", "fine", "agreed"
    ]
    rejected_words = [
        "rejected", "reject", 
        "no", "nope", "stop", "cancel", "deny"
    ]
    
    if any(word in first_lines for word in approved_words):
        logger.info("[EmailGraph] Rule-based classification: APPROVED")
        return "APPROVED"
        
    if any(word in first_lines for word in rejected_words):
        logger.info("[EmailGraph] Rule-based classification: REJECTED")
        return "REJECTED"

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
    
    # 1. If this is an original request that just got validated:
    if state.get("status") == "PENDING_APPROVAL":
        import email.utils
        # Extract plain email from the sender string (e.g. 'John Doe <john@example.com>' -> 'john@example.com')
        _, email_addr = email.utils.parseaddr(state.get("sender", ""))
        state["requester_email"] = email_addr if email_addr else state.get("sender")
        
        # Save state to Redis using message_id
        redis_client.set(f"email_request:{state['message_id']}", json.dumps(state))
        logger.info(f"[EmailGraph] Original request saved. Waiting for approval reply on thread {state['message_id']}.")
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
            
        if pending_approvals:
            import email.utils
            _, reply_sender = email.utils.parseaddr(state.get("sender", ""))
            reply_sender = reply_sender.lower() if reply_sender else ""
            
            if reply_sender != settings.UPDATE_APPROVAL_ADMIN_EMAIL.lower():
                logger.warning(f"[EmailGraph] Ignoring approval from {reply_sender} - not the admin.")
                return {**state, "status": "INVALID", "error_message": "Unauthorized approver."}
                
            body = state.get("body", "")
            intent = analyze_approval_intent(body)
            
            if intent == "APPROVED":
                logger.info("[EmailGraph] Admin approved the mid-flight update!")
                from app.tasks.installation_tasks import resume_approved_update
                from datetime import datetime
                for req in pending_approvals:
                    req.status = "APPROVED"
                    req.approved_by = reply_sender
                    req.approved_at = datetime.utcnow()
                    approval_repo.update(db, req)
                    resume_approved_update.delay(req.id)
                return {**state, "status": "APPROVED", "error_message": "Admin mid-flight approval processed."}
            elif intent == "REJECTED":
                for req in pending_approvals:
                    req.status = "REJECTED"
                    approval_repo.update(db, req)
                return {**state, "status": "REJECTED"}
            else:
                return {**state, "status": "INVALID", "error_message": "Agent could not confirm approval."}
    finally:
        db.close()

    original_state = None
    original_msg_id = None
    
    for tid in thread_ids_to_check:
        if not tid: continue
        data = redis_client.get(f"email_request:{tid}")
        if data:
            original_state = json.loads(data)
            original_msg_id = tid
            break
            
    if not original_state:
        # Fallback: Subject-based matching for email clients that strip headers
        import re
        def clean_email_subject(subj: str) -> str:
            cleaned = subj
            # Match pattern like re:, fwd:, re[2]:, fwd[2]: at start (case-insensitive, optional spaces/brackets)
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
            logger.info(f"[EmailGraph] Trying subject-based fallback for: '{clean_subject}'")
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
        # If it was already INVALID (no install intent), keep it INVALID.
        # If it was RECEIVED (but no install intent), make it INVALID.
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
        redis_client.set(f"email_request:{original_msg_id}", json.dumps(original_state))
        return {**state, "status": "REJECTED"}
        
    if intent == "APPROVED":
        reply_sender = state.get("sender", "").lower()
        logger.info(f"[EmailGraph] Request {original_msg_id} was APPROVED by {reply_sender}!")
        original_state["status"] = "APPROVED"
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
