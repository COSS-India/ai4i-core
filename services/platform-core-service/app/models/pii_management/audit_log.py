"""ORM model for the audit_logs table (PII database)."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.pii_management import PiiBase


class AuditLog(PiiBase):
    """Record of a single /redact invocation — written asynchronously after every call."""

    __tablename__ = "audit_logs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    trace_id       = Column(UUID(as_uuid=False), nullable=True)
    tenant_id      = Column(String(50),  nullable=True)
    domain_id      = Column(String(50),  nullable=True)
    target_context = Column(String(20),  nullable=True)
    pii_count      = Column(Integer,     nullable=True)
    processing_ms  = Column(Integer,     nullable=True)
    trace_json     = Column(JSONB,        nullable=True)
    created_at     = Column(DateTime,    server_default=func.current_timestamp(), nullable=True)
