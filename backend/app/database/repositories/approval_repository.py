from sqlalchemy.orm import Session
from app.database.models.approval import ApprovalRequest
from typing import Optional, List

class ApprovalRepository:
    def get(self, db: Session, approval_id: str) -> Optional[ApprovalRequest]:
        return db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        
    def get_pending_by_thread(self, db: Session, thread_id: str) -> List[ApprovalRequest]:
        # Sometimes email servers change In-Reply-To to message ID, so we check both
        return db.query(ApprovalRequest).filter(
            ApprovalRequest.status == "PENDING",
            (ApprovalRequest.original_message_id == thread_id) | (ApprovalRequest.original_thread_id == thread_id)
        ).all()

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
