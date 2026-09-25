from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func

from app.models import Base


class TenantNotificationSubscription(Base):
    """An institution's subscription to one INSTITUTION-scope catalog row.

    Row absence for a (notification_id, tenant_id) pair also means
    "unsubscribed" — the seed migration inserts one row per tenant per
    notification with ``subscribed=false`` so every read has a row to join
    against, but nothing in the API relies on a row necessarily existing.

    ``subscribed`` is never mutated by a catalog row's own ``scope``
    changing — a GLOBAL-scope row's effective subscription is always "on"
    regardless of what's stored here, and reverting it back to INSTITUTION
    scope restores whatever this column still holds. ``recipients`` (the
    institution's additional recipients, alongside its own tenant admin) is
    likewise untouched by scope changes.

    ``tenant_id`` is a plain string, not a real FK — tenants live in
    auth-service's own database (ai4iplatform_auth), a different Postgres
    database from this table's, so no cross-database FK is possible (same
    convention as ledger_notification_alert.tenant_id).
    """

    __tablename__ = "tenant_notification_subscription"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "tenant_id", name="uq_tenant_notification_subscription_identity"
        ),
        Index("ix_tenant_notification_subscription_tenant_id", "tenant_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(
        BigInteger,
        ForeignKey("configs_notification_alert.id", name="fk_tenant_notification_subscription_notification_id"),
        nullable=False,
    )
    tenant_id = Column(String(255), nullable=False)
    subscribed = Column(Boolean, nullable=False, server_default="false")
    recipients = Column(ARRAY(String(255)), nullable=False, server_default="{}")
    created_by = Column(String(255), nullable=True)
    updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
