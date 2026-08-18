import time
import uuid
import threading
from app.core.config import settings
from app.core.logger import logger
from app.mail_listener.imap_client import IMAPClient
from app.mail_listener.email_parser import parse_email
# pyrefly: ignore [missing-import]
import redis

# Redis client for duplicate protection
redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)

def process_email(client: IMAPClient, email_id: bytes, msg):
    parsed = parse_email(msg)
    message_id = parsed.get("message_id")
    body = parsed.get("body", "")
    subject = parsed.get("subject", "")
    
    if not message_id:
        logger.warning("[EmailListener] Message missing Message-ID. Ignoring.")
        return
    
    sender = parsed.get("sender", "Unknown")
    logger.info(f"[EmailListener] Processing email event from: {sender} (Message-ID: {message_id})")
    
    from app.graph.email.graph import create_email_intake_graph
    from datetime import datetime
    
    initial_state = {
        "message_id": message_id,
        "sender": sender,
        "in_reply_to": parsed.get("in_reply_to"),
        "references": parsed.get("references", []),
        "subject": subject,
        "body": body,
        "recipient": parsed.get("to", ""),
        "status": "RECEIVED",
        "received_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Avoid duplicate processing of the same exact message_id (if IMAP gives it to us again)
    if redis_client.get(f"email_processed:{message_id}"):
        logger.info(f"[EmailListener] Email {message_id} already processed. Skipping.")
        return
        
    redis_client.set(f"email_processed:{message_id}", "true", ex=86400 * 7) # Keep duplicate protection for 7 days
    
    graph = create_email_intake_graph()
    try:
        final_state = graph.invoke(initial_state)
        logger.info(f"[EmailListener] Graph finished for {message_id} with status: {final_state.get('status')}")
        client.mark_as_read(email_id)
    except Exception as e:
        logger.error(f"[EmailListener] Error executing email graph: {str(e)}")


def polling_loop():
    logger.info("[EmailListener] Starting IMAP polling loop...")
    client = IMAPClient()
    
    while True:
        try:
            if client.connect():
                logger.info("[EmailListener] Checking mailbox...")
                emails = client.fetch_unread_emails()
                
                for email_id, msg in emails:
                    try:
                        process_email(client, email_id, msg)
                    except Exception as e:
                        logger.error(f"[EmailListener] Error processing email: {e}")
                
                client.disconnect()
        except Exception as e:
            logger.error(f"[EmailListener] IMAP polling error: {e}")
            
        time.sleep(settings.IMAP_POLL_INTERVAL)

def start_polling():
    if not getattr(settings, 'ENABLE_IMAP_LISTENER', False):
        logger.info("IMAP Listener is disabled. Set ENABLE_IMAP_LISTENER=true to enable.")
        return
        
    thread = threading.Thread(target=polling_loop, daemon=True)
    thread.start()
