"""ORM mapping of ``audit_logs`` in ``ai4iplatform_core``.

The table is created by the ai4iplatform_core Alembic chain; this module only
maps it. It uses its own declarative base so importing it never adds the
table to a service's own metadata (and so to that service's autogenerate).
"""

from sqlalchemy import BigInteger, Column, DateTime, Identity, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

AuditBase = declarative_base()


class AuditLog(AuditBase):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, Identity(always=False), primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    entity_name = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    previous_state = Column(JSONB, nullable=True)
    new_state = Column(JSONB, nullable=True)
    message = Column(Text, nullable=True)
    performed_by = Column(UUID(as_uuid=True), nullable=True)
    trace_id = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_entity", entity_name, entity_id, created_at.desc()),
        Index("ix_audit_logs_created_at", created_at),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} {self.entity_name}:{self.entity_id} "
            f"{self.action}>"
        )
