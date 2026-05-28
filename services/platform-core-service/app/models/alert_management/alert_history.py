"""ORM model for `alert_history` — append-only audit log of triggered alerts.

Lifted from alert-management-service/models.py:201-230 with:
  - `organization` column dropped (org-extraction logic removed).
  - The `AlertConfigAuditLog` table is NOT migrated — audit-logging feature
    is being dropped per the migration plan.
"""

from sqlalchemy import BigInteger, Column, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id = Column(BigInteger, primary_key=True)
    alert_name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, server_default="firing")
    receiver = Column(String(255), nullable=False)
    notified_display = Column(String(500), nullable=True)
    tenant = Column(String(255), nullable=True)
    labels = Column(JSONB, nullable=True)
    annotations = Column(JSONB, nullable=True)
    fingerprint = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("idx_alert_history_triggered_at", triggered_at.desc()),
        Index("idx_alert_history_category", "category"),
        Index("idx_alert_history_severity", "severity"),
        Index("idx_alert_history_alert_name", "alert_name"),
        Index("idx_alert_history_tenant", "tenant"),
    )
