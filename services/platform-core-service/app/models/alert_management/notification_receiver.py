"""ORM model for `notification_receivers`.

Lifted from alert-management-service/models.py:111-149 with:
  - `organization` column dropped.
  - The composite `(organization, receiver_name)` uniqueness becomes a single
    unique constraint on `receiver_name`. Receiver names are now globally
    unique (no more per-org namespace).
"""

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.models import Base


class NotificationReceiver(Base):
    __tablename__ = "notification_receivers"
    __table_args__ = (
        UniqueConstraint("receiver_name", name="unique_receiver_name"),
        Index("idx_notification_receivers_enabled", "enabled"),
        Index("idx_notification_receivers_category", "category"),
        Index("idx_notification_receivers_severity", "severity"),
    )

    id = Column(Integer, primary_key=True)
    receiver_name = Column(String(255), nullable=False)
    rule_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False, server_default="application")
    severity = Column(String(20), nullable=False, server_default="warning")
    email_to = Column(ARRAY(Text), nullable=False, server_default="{}")
    rbac_role = Column(String(50), nullable=True)
    alert_names = Column(ARRAY(Text), nullable=True)
    tenant = Column(String(255), nullable=True)
    email_subject_template = Column(Text, nullable=True)
    email_body_template = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
