from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models import Base


class LedgerNotificationAlert(Base):
    """Producer-only record of what was already produced — one row per
    (notification, tenant, subject). Written only by the shared producer
    pipeline (ai4i_core.kafka); the consumer never reads or writes it.

    A BAND row holds ``current_band`` + ``triggered``; a STATE row holds
    ``state_hash`` + ``triggered`` — exactly one of the two values is set.
    MONITORING rows use tenant_id 'PLATFORM'. No channel and no delivery
    status: delivery belongs to the consumer, keyed by ``last_event_id``.
    """

    __tablename__ = "ledger_notification_alert"
    __table_args__ = (
        UniqueConstraint("notification_id", "tenant_id", "subject", name="uq_ledger_notification_alert_identity"),
        CheckConstraint("jsonb_typeof(subject) = 'object'", name="ck_ledger_notification_alert_subject"),
        CheckConstraint(
            "(current_band IS NULL) <> (state_hash IS NULL)", name="ck_ledger_notification_alert_one_value"
        ),
        Index("ix_ledger_notification_alert_tenant_updated", "tenant_id", text("updated_at DESC")),
        Index("ix_ledger_notification_alert_open", "notification_id", postgresql_where=text("triggered")),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(
        BigInteger,
        ForeignKey("configs_notification_alert.id", name="fk_ledger_notification_alert_notification_id"),
        nullable=False,
    )
    tenant_id = Column(String(255), nullable=False)
    subject = Column(JSONB, nullable=False, server_default="{}")
    current_band = Column(Numeric(12, 4), nullable=True)
    state_hash = Column(CHAR(64), nullable=True)
    triggered = Column(Boolean, nullable=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    last_event_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
