import imaplib
import email
from email.message import Message
from typing import List, Optional, Tuple
from app.core.logger import logger
from app.core.config import settings

class IMAPClient:
    def __init__(self):
        self.host = settings.IMAP_HOST
        self.port = settings.IMAP_PORT
        self.username = settings.IMAP_USERNAME
        self.password = settings.IMAP_PASSWORD
        self.use_ssl = settings.IMAP_USE_SSL
        self.mail: Optional[imaplib.IMAP4] = None

    def connect(self) -> bool:
        if not self.host or not self.username or not self.password:
            logger.error("IMAPClient: Missing IMAP credentials in configuration.")
            return False

        try:
            if self.use_ssl:
                self.mail = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self.mail = imaplib.IMAP4(self.host, self.port)
                
            self.mail.login(self.username, self.password)
            logger.debug(f"IMAPClient: Connected to {self.username}@{self.host}")
            return True
        except Exception as e:
            logger.error(f"IMAPClient: Connection failed: {e}")
            return False

    def fetch_unread_emails(self, mailbox: str = "inbox") -> List[Tuple[bytes, Message]]:
        if not self.mail:
            logger.error("IMAPClient: Not connected.")
            return []

        try:
            self.mail.select(mailbox)
            # Use ALL instead of UNSEEN to make testing easier if emails are already read
            status, messages = self.mail.search(None, 'ALL')
            
            if status != 'OK':
                logger.error(f"IMAPClient: Search failed with status {status}")
                return []
                
            email_ids = messages[0].split()
            # Only process the 5 most recent emails to avoid processing the whole inbox
            recent_email_ids = email_ids[-5:] if len(email_ids) > 5 else email_ids
            
            fetched_emails = []
            
            for email_id in recent_email_ids:
                status, msg_data = self.mail.fetch(email_id, '(RFC822)')
                if status == 'OK':
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            fetched_emails.append((email_id, msg))
                            
            return fetched_emails
        except Exception as e:
            logger.error(f"IMAPClient: Fetch failed: {e}")
            return []

    def fetch_email_by_message_id(self, message_id: str, mailbox: str = "inbox") -> Optional[Message]:
        if not self.mail:
            return None
            
        try:
            self.mail.select(mailbox)
            # Search by HEADER Message-ID
            search_str = f'HEADER Message-ID "{message_id}"'
            status, messages = self.mail.search(None, search_str)
            
            if status == 'OK' and messages[0]:
                email_id = messages[0].split()[0]
                status, msg_data = self.mail.fetch(email_id, '(RFC822)')
                if status == 'OK':
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            return email.message_from_bytes(response_part[1])
        except Exception as e:
            logger.error(f"IMAPClient: Failed to fetch by Message-ID: {e}")
        return None

    def mark_as_read(self, email_id: bytes):
        if self.mail:
            try:
                self.mail.store(email_id, '+FLAGS', '\\Seen')
            except Exception as e:
                logger.error(f"IMAPClient: Failed to mark {email_id} as read: {e}")

    def disconnect(self):
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except Exception as e:
                logger.error(f"IMAPClient: Error during disconnect: {e}")
            finally:
                self.mail = None
