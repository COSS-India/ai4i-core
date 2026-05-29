"""ORM model for `routing_rules`.

Lifted from alert-management-service/models.py:152-198 with:
  - `organization` column dropped.
  - Composite `(organization, rule_name)` uniqueness becomes a single unique
    constraint on `rule_name`.
"""

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.models import Base


class RoutingRule(Base):
    __tablename__ = "routing_rules"
    __table_args__ = (
        UniqueConstraint("rule_name", name="unique_rule_name"),
        Index("idx_routing_rules_receiver_id", "receiver_id"),
        Index("idx_routing_rules_enabled", "enabled"),
        Index("idx_routing_rules_priority", "priority"),
        Index("idx_routing_rules_match_severity", "match_severity"),
        Index("idx_routing_rules_match_category", "match_category"),
    )

    id = Column(Integer, primary_key=True)
    rule_name = Column(String(255), nullable=False)
    receiver_id = Column(
        Integer,
        ForeignKey("notification_receivers.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_severity = Column(String(20), nullable=True)
    match_category = Column(String(50), nullable=True)
    match_alert_type = Column(String(50), nullable=True)
    match_alert_names = Column(ARRAY(Text), nullable=True)
    match_tenant_id = Column(String(255), nullable=True)
    group_by = Column(ARRAY(Text), nullable=True)
    group_wait = Column(String(20), nullable=True, server_default="10s")
    group_interval = Column(String(20), nullable=True, server_default="10s")
    repeat_interval = Column(String(20), nullable=True, server_default="12h")
    continue_routing = Column(Boolean, nullable=True, server_default="false")
    priority = Column(Integer, nullable=True, server_default="100")
    enabled = Column(Boolean, nullable=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
