"""ORM model for the audit_log table."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.models import Base


class PolicyAuditLog(Base):
    """Record of the policies applied to a single model request.

    Named PolicyAuditLog because AuditLog is already taken by pii_audit_logs.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Elements reference policy.id; not enforced by the database.
    policy_id = Column(ARRAY(Integer), nullable=True)
    trace_id = Column(String(64), nullable=True, index=True)
    model_request = Column(JSONB, nullable=True)
    response = Column(JSONB, nullable=True)
    guardrail_info = Column(JSONB, nullable=True)
