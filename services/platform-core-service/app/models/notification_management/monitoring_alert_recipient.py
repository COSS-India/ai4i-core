from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.sql import func

from app.models import Base


class MonitoringAlertRecipient(Base):
    """One resolved recipient (a platform user id) of one MONITORING-type
    catalog row.

    Monitoring alerts have no scope and no tenant — they go to every user
    holding a role selected in the row's ``recipient_roles`` (ADMIN and/or
    MODERATOR). Those user ids are resolved from ai4iplatform_auth and
    stored here by the monitoring catalog PATCH, which rebuilds a
    notification's rows wholesale whenever recipient_roles changes.
    ``role`` records which selected role pulled the user in.

    ``user_id`` is a plain string, not a real FK — users live in
    auth-service's own database (same convention as
    tenant_notification_subscription.recipients).
    """

    __tablename__ = "monitoring_alert_recipient"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_monitoring_alert_recipient_identity"),
        Index("ix_monitoring_alert_recipient_notification_id", "notification_id"),
        CheckConstraint("role IN ('ADMIN', 'MODERATOR')", name="ck_monitoring_alert_recipient_role"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(
        BigInteger,
        ForeignKey(
            "configs_notification_alert.id",
            name="fk_monitoring_alert_recipient_notification_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id = Column(String(255), nullable=False)
    role = Column(String(64), nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
