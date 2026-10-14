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
            
            # Fetch ALL email IDs to find the highest sequence numbers
            status, messages = self.mail.search(None, 'ALL')
            
            if status != 'OK' or not messages[0]:
                return []
                
            all_id_list = messages[0].split()
            
            # Fetch the most recent N emails regardless of read status
            # (Captures emails the admin might have manually read on their phone)
            max_emails = settings.IMAP_MAX_EMAILS
            recent_ids = set(all_id_list[-max_emails:] if len(all_id_list) > max_emails else all_id_list)
            
            # Also fetch ANY UNSEEN (unread) emails
            # (Captures bulk spikes of > N emails that arrived together)
            status_unseen, unseen_msgs = self.mail.search(None, 'UNSEEN')
            unseen_ids = set(unseen_msgs[0].split()) if (status_unseen == 'OK' and unseen_msgs[0]) else set()
            
            # Union: recent + unseen (Never miss a reply, never miss a bulk spike)
            email_ids_to_fetch = list(recent_ids | unseen_ids)
            
            fetched_emails = []
            
            for email_id in email_ids_to_fetch:
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
