from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.sql import func

from ai4i_core.kafka import FailureStage, Producer

from app.models import Base

_STAGE_ENUM = ENUM(*[s.value for s in FailureStage], name="notification_failure_stage_enum", create_type=False)
_PRODUCERS = ", ".join(f"'{p.value}'" for p in Producer)


class NotificationAlertFailureLog(Base):
    """Write-once record of a producer-side failure before the Kafka hand-off
    (written by ai4i_core.kafka). No status or retry columns: the producer
    never retries; delivery retries belong to the consumer."""

    __tablename__ = "notification_alert_failure_log"
    __table_args__ = (
        CheckConstraint(f"producer IN ({_PRODUCERS})", name="ck_failure_log_producer"),
        CheckConstraint("jsonb_typeof(error_detail) = 'object'", name="ck_failure_log_detail"),
        Index("ix_failure_log_name_created", "notification_name", text("created_at DESC")),
        Index("ix_failure_log_event", "event_id", postgresql_where=text("event_id IS NOT NULL")),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(UUID(as_uuid=True), nullable=True)
    notification_name = Column(String(64), nullable=False)
    notification_id = Column(
        BigInteger,
        ForeignKey(
            "configs_notification_alert.id",
            name="fk_notification_alert_failure_log_notification_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    tenant_id = Column(String(255), nullable=True)
    subject = Column(JSONB, nullable=True)
    producer = Column(String(64), nullable=False)
    pod_name = Column(String(255), nullable=True)
    stage = Column(_STAGE_ENUM, nullable=False)
    error_code = Column(String(64), nullable=False)
    error_message = Column(Text, nullable=False)
    error_detail = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
