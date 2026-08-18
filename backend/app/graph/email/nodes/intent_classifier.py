import json
from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.llm_service import LLMService

def classify_intent(state: EmailState) -> EmailState:
    logger.info(f"[EmailGraph] Intent classifier processing: {state.get('message_id')}")
    
    if state.get("status") != "RECEIVED":
        return state
        
    combined_text = f"Subject: {state.get('subject', '')}\nBody: {state.get('body', '')}"
    
    prompt = f"""You are an intelligent email parsing agent for a software deployment system.
Analyze the following email and determine if it is requesting a software installation.

Email Content:
{combined_text}

If the user is asking to install software, extract the following:
1. application_name: The name of the software (e.g. Chrome, Firefox, Node.js). If you cannot deduce a specific software name, return null.
2. target_host_ip: The IP address of the target machine. If no IP is found, return null.
3. version: The requested version. If no version is specified, return "latest".

CRITICAL RULE: If this email is a REPLY to a previous request (for example, the subject starts with "Re:" AND the body says "Approved", "Yes", "No", etc.), it is NOT a new installation request. You must return null for application_name and target_host_ip, even if the quoted text below it mentions installing software.
If the email is just "Approved", "Yes", "Hello", or empty, return null for application_name and target_host_ip.

Return ONLY a valid JSON object matching this schema:
{{
    "application_name": "string or null",
    "target_host_ip": "string or null",
    "version": "string or null"
}}
"""
    
    try:
        response_text = LLMService.generate(prompt, json_mode=True)
        
        # Robustly clean the LLM output in case it wrapped it in markdown
        import re
        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?|```$', '', clean_text).strip()
            
        if not clean_text:
            logger.error("[EmailGraph] LLM returned empty response")
            return {**state, "status": "INVALID", "error_message": "LLM returned empty response"}
            
        # Parse the JSON response
        data = json.loads(clean_text)
        
        app_name = data.get("application_name")
        ip_addr = data.get("target_host_ip")
        version = data.get("version", "latest")
        
        if app_name and ip_addr:
            # Check if the extracted "app_name" is bogus (like "in 192")
            if app_name.lower().startswith("in ") or app_name.lower().startswith("on "):
                logger.info(f"[EmailGraph] LLM extracted bogus app name: {app_name}. Marking as invalid.")
                return {**state, "status": "INVALID", "error_message": "Could not identify a valid application name."}
                
            logger.info(f"[EmailGraph] Installation request detected via Agent: {app_name} on {ip_addr}")
            return {
                **state,
                "application_name": app_name,
                "target_host_ip": ip_addr,
                "version": version
            }
            
        logger.info("[EmailGraph] Agent determined this is not a new installation request. Leaving status as RECEIVED for approval_gate.")
        return state
        
    except Exception as e:
        logger.error(f"[EmailGraph] Agent intent classification failed: {str(e)}. Raw output was: {response_text}")
        return {**state, "status": "FAILED", "error_message": f"LLM error: {str(e)}"}
