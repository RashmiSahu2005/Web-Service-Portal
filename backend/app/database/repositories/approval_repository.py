from sqlalchemy.orm import Session
from app.database.models.approval import ApprovalRequest
from typing import Optional, List

class ApprovalRepository:
    def get(self, db: Session, approval_id: str) -> Optional[ApprovalRequest]:
        return db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        
    def get_pending_by_thread(self, db: Session, thread_id: str) -> List[ApprovalRequest]:
        # Only match the exact message ID of the approval email sent to the admin.
        # This prevents accidental approvals by replying to the original requester's thread.
        return db.query(ApprovalRequest).filter(
            ApprovalRequest.status == "PENDING",
            ApprovalRequest.admin_message_id == thread_id
        ).all()

    def get_and_lock_pending_by_thread(self, db: Session, thread_id: str) -> List[ApprovalRequest]:
        """SELECT FOR UPDATE — acquires a row lock so concurrent workers cannot both transition
        the same approval. Must be called inside an open transaction."""
        return db.query(ApprovalRequest).filter(
            ApprovalRequest.status == "PENDING",
            ApprovalRequest.admin_message_id == thread_id
        ).with_for_update().all()

    def get_any_by_thread(self, db: Session, thread_id: str) -> Optional[ApprovalRequest]:
        """Return the most recent approval record for this thread regardless of status.
        Used to detect ALREADY_PROCESSED scenarios without locking."""
        return db.query(ApprovalRequest).filter(
            ApprovalRequest.admin_message_id == thread_id
        ).order_by(ApprovalRequest.created_at.desc()).first()

    def create(self, db: Session, approval: ApprovalRequest) -> ApprovalRequest:
        db.add(approval)
        db.commit()
        db.refresh(approval)
        return approval

    def update(self, db: Session, approval: ApprovalRequest) -> ApprovalRequest:
        db.commit()
        db.refresh(approval)
        return approval

approval_repo = ApprovalRepository()
