import email
from email.message import Message
from typing import Dict, Any, Optional

def extract_body(msg: Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            if content_type == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body += payload.decode(part.get_content_charset() or 'utf-8', errors='replace') + "\n"
            # HTML fallback could be processed here if needed, but plain text is prioritized for simplicity
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain" or content_type == "text/html":
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(msg.get_content_charset() or 'utf-8', errors='replace')
                
    return body.strip()

def parse_email(msg: Message) -> Dict[str, Any]:
    """
    Parses an email.message.Message into a structured dictionary.
    Extracts headers crucial for thread correlation.
    """
    subject = msg.get("Subject", "")
    # Decode subject if it's encoded
    decoded_subject = email.header.decode_header(subject)[0]
    if isinstance(decoded_subject[0], bytes):
        try:
            subject = decoded_subject[0].decode(decoded_subject[1] or 'utf-8')
        except Exception:
            subject = decoded_subject[0].decode('utf-8', errors='replace')
    else:
        subject = decoded_subject[0]

    return {
        "sender": msg.get("From", ""),
        "recipient": msg.get("To", ""),
        "subject": subject,
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", "").strip("<>"),
        "in_reply_to": msg.get("In-Reply-To", "").strip("<>"),
        "references": [ref.strip("<>") for ref in msg.get("References", "").split()] if msg.get("References") else [],
        "body": extract_body(msg)
    }
