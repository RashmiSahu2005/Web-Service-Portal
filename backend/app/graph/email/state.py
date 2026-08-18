from typing import TypedDict, Optional, List
from datetime import datetime

class EmailState(TypedDict, total=False):
    # Core email identifiers
    message_id: str
    in_reply_to: Optional[str]
    references: List[str]
    
    # Original email content
    subject: str
    body: str
    sender: str
    recipient: str
    
    # Extracted fields
    application_name: Optional[str]
    application_id: Optional[str]
    version: Optional[str]
    target_host_ip: Optional[str]
    host_id: Optional[str]
    ticket_id: Optional[str]
    
    # Lifecycle Status
    # RECEIVED, PENDING_APPROVAL, APPROVED, REJECTED, INVALID, COMPLETED, FAILED
    status: str
    
    # Final mappings
    job_id: Optional[str]
    
    # Error tracking
    error_message: Optional[str]
    
    # Timestamps
    received_at: datetime
    updated_at: datetime
