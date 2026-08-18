import json
from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.llm_service import LLMService
import redis

redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

def analyze_approval_intent(text: str) -> str:
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
        raw_subj = state.get("subject", "")
        if raw_subj and raw_subj.lower().startswith("re:"):
            clean_subject = raw_subj.lower().replace("re:", "", 1).strip()
            logger.info(f"[EmailGraph] Trying subject-based fallback for: '{clean_subject}'")
            for key in redis_client.scan_iter("email_request:*"):
                data = redis_client.get(key)
                if data:
                    parsed_state = json.loads(data)
                    orig_subj = parsed_state.get("subject", "").lower().strip()
                    if orig_subj == clean_subject and parsed_state.get("status") == "PENDING_APPROVAL":
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
        original_sender = original_state.get("sender", "").lower()
        
        # Enforce that the approval must come from the original requester (for MVP demo purposes)
        if reply_sender != original_sender:
            logger.warning(f"[EmailGraph] Approval ignored: Sender {reply_sender} does not match original requester {original_sender}.")
            return {**state, "status": "INVALID", "error_message": "Approval must come from the original requester."}
            
        logger.info(f"[EmailGraph] Request {original_msg_id} was APPROVED by {reply_sender}!")
        original_state["status"] = "APPROVED"
        redis_client.set(f"email_request:{original_msg_id}", json.dumps(original_state))
        
        # Merge the original extracted details into the current state so it can proceed to mapping
        return {
            **state,
            "status": "APPROVED",
            "application_name": original_state.get("application_name"),
            "application_id": original_state.get("application_id"),
            "version": original_state.get("version"),
            "target_host_ip": original_state.get("target_host_ip"),
            "host_id": original_state.get("host_id"),
        }
        
    logger.info(f"[EmailGraph] Reply on thread {original_msg_id} was classified as NEITHER.")
    return {**state, "status": "INVALID", "error_message": "Agent could not confirm approval or rejection."}
