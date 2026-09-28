import json
import re
from app.core.logger import logger
from app.graph.email.state import EmailState
from app.services.llm_service import LLMService

def _try_repair_json(raw: str) -> dict | None:
    """Attempt to salvage a truncated/malformed JSON response from the LLM."""
    try:
        apps_match = re.search(r'"applications"\s*:\s*(\[.*?\])', raw, re.DOTALL)
        ip_match = re.search(r'"target_host_ip"\s*:\s*(".*?"|null)', raw)
        if apps_match:
            apps_raw = apps_match.group(1)
            # Remove any non-object elements from the array (e.g. stray strings like "target_host_ip")
            apps_raw = re.sub(r',\s*"[^"]*"(?=\s*[\],])', '', apps_raw)
            apps = json.loads(apps_raw)
            ip = None
            if ip_match:
                ip_val = ip_match.group(1).strip()
                ip = None if ip_val == "null" else ip_val.strip('"')
            return {"applications": apps, "target_host_ip": ip}
    except Exception:
        pass
    return None

def classify_intent(state: EmailState) -> EmailState:
    logger.info(f"[EmailGraph] Intent classifier processing: {state.get('message_id')}")

    if state.get("status") != "RECEIVED":
        return state

    in_reply_to = state.get("in_reply_to")
    references = state.get("references", [])
    subject = state.get("subject", "").lower().strip()
    
    # Fast path: If this is obviously a reply, skip LLM intent classification for a *new* request.
    # It will remain 'RECEIVED' and flow to approval_gate to be processed as a reply.
    is_reply = bool(
        in_reply_to or 
        references or 
        subject.startswith("re:") or 
        subject.startswith("fwd:") or 
        subject.startswith("aw:") or 
        subject.startswith("wg:")
    )
    
    if is_reply:
        logger.info("[EmailGraph] Email identified as a reply via headers/subject. Leaving status as RECEIVED for approval_gate.")
        return state


    combined_text = f"Subject: {state.get('subject', '')}\nBody: {state.get('body', '')}"

    prompt = f"""Analyze the following email and extract software installation details.

Email Content:
{combined_text}

CRITICAL RULE: If the email is a REPLY (starts with "Re:", or contains words like "Approved", "Yes", "go ahead") to a previous thread, it is NOT a new request. Return an empty applications list.

Return ONLY a valid JSON object with exactly these two top-level keys. Do not nest target_host_ip inside applications.

{{
    "applications": [
        {{
            "name": "string",
            "version": "string",
            "operation": "INSTALL or UPDATE"
        }}
    ],
    "target_host_ip": "string or null"
}}

Rules:
- "applications" is a JSON array of objects. Each object has exactly "name", "version", and "operation".
- "operation" MUST be explicitly set to either "INSTALL" or "UPDATE". Use "INSTALL" if not explicitly requested as an update.
- "target_host_ip" is a top-level key, NOT inside applications. It is the IP address from the email, or null if none.
- If no software is mentioned, return an empty array for applications.
- Use "latest" for version if not specified.
- Return ONLY the JSON. No markdown fences, no explanation, no extra text.
"""

    response_text = ""
    try:
        response_text = LLMService.generate(prompt, json_mode=True)

        clean_text = response_text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r'^```(?:json)?|```$', '', clean_text, flags=re.MULTILINE).strip()

        if not clean_text:
            logger.error("[EmailGraph] LLM returned empty response")
            return {**state, "status": "INVALID", "error_message": "LLM returned empty response"}

        # Try direct parse first, then attempt JSON repair on failure
        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError:
            logger.warning(f"[EmailGraph] JSON parse failed, attempting repair. Raw: {clean_text[:200]}")
            data = _try_repair_json(clean_text)
            if data is None:
                logger.error(f"[EmailGraph] JSON repair also failed. Raw: {clean_text[:200]}")
                return {**state, "status": "INVALID", "error_message": "Failed to parse LLM response"}

        apps = data.get("applications", [])
        ip_addr = data.get("target_host_ip")

        valid_apps = []
        for app in apps:
            if not isinstance(app, dict):
                continue  # Skip stray non-object elements
            app_name = (app.get("name") or "").strip()
            if app_name and not (app_name.lower().startswith("in ") or app_name.lower().startswith("on ")):
                valid_apps.append({
                    "name": app_name,
                    "version": app.get("version", "latest"),
                    "operation": app.get("operation", "INSTALL").upper()
                })

        if valid_apps:
            app_names = [a["name"] for a in valid_apps]
            logger.info(f"[EmailGraph] Installation request detected via Agent: {', '.join(app_names)} on {ip_addr}")

            return {
                **state,
                "applications": valid_apps,
                "application_name": valid_apps[0]["name"],
                "version": valid_apps[0]["version"],
                "target_host_ip": ip_addr
            }

        logger.info("[EmailGraph] Agent determined this is not a new installation request. Leaving status as RECEIVED for approval_gate.")
        return state

    except Exception as e:
        logger.error(f"[EmailGraph] Agent intent classification failed: {str(e)}. Raw output was: {response_text}")
        return {**state, "status": "INVALID", "error_message": f"LLM error: {str(e)}"}
