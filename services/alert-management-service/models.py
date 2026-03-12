"""
SQLAlchemy models for dynamic alert configuration in alerting_db.

These models mirror the schema defined in init_alerting_db_commands.sql and
are intended for use with Alembic migrations and tooling, not for the
runtime CRUD paths (which use asyncpg directly in alert_management.py).
"""

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    Float,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class AlertDefinition(Base):
    __tablename__ = "alert_definitions"
    __table_args__ = (
        UniqueConstraint("name", name="unique_alert_name"),
        Index("idx_alert_definitions_organization", "organization"),
        Index("idx_alert_definitions_enabled", "enabled"),
        Index("idx_alert_definitions_category", "category"),
        Index("idx_alert_definitions_severity", "severity"),
        Index(
            "idx_alert_definitions_organization_enabled",
            "organization",
            "enabled",
        ),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    promql_expr = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, server_default="application")
    sub_category = Column(String(100), nullable=True)
    signal = Column(String(100), nullable=True)
    signal_metric = Column(String(100), nullable=True)
    condition_operator = Column(String(10), nullable=True)
    severity = Column(String(20), nullable=False)
    urgency = Column(String(20), nullable=True, server_default="medium")
    alert_type = Column(String(50), nullable=True)
    scope = Column(String(50), nullable=True)
    service = Column(ARRAY(Text), nullable=True)
    evaluation_interval = Column(String(20), nullable=True, server_default="30s")
    for_duration = Column(String(20), nullable=True, server_default="5m")
    threshold_value = Column(Float, nullable=True)
    threshold_unit = Column(String(50), nullable=True)
    enabled = Column(Boolean, nullable=True, server_default="true")
    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)


class AlertAnnotation(Base):
    __tablename__ = "alert_annotations"
    __table_args__ = (
        UniqueConstraint(
            "alert_definition_id",
            "annotation_key",
            name="unique_alert_annotation_key",
        ),
        Index("idx_alert_annotations_alert_def_id", "alert_definition_id"),
    )

    id = Column(Integer, primary_key=True)
    alert_definition_id = Column(
        Integer,
        ForeignKey("alert_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    annotation_key = Column(String(50), nullable=False)
    annotation_value = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )


class NotificationReceiver(Base):
    __tablename__ = "notification_receivers"
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "receiver_name",
            name="unique_organization_receiver_name",
        ),
        Index("idx_notification_receivers_organization", "organization"),
        Index("idx_notification_receivers_enabled", "enabled"),
        Index("idx_notification_receivers_category", "category"),
        Index("idx_notification_receivers_severity", "severity"),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=False)
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
    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    created_by = Column(String(100), nullable=True)


class RoutingRule(Base):
    __tablename__ = "routing_rules"
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "rule_name",
            name="unique_organization_rule_name",
        ),
        Index("idx_routing_rules_organization", "organization"),
        Index("idx_routing_rules_receiver_id", "receiver_id"),
        Index("idx_routing_rules_enabled", "enabled"),
        Index("idx_routing_rules_priority", "priority"),
        Index("idx_routing_rules_match_severity", "match_severity"),
        Index("idx_routing_rules_match_category", "match_category"),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=False)
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
    created_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    created_by = Column(String(100), nullable=True)


class AlertHistory(Base):
    __tablename__ = "alert_history"
    __table_args__ = (
        Index("idx_alert_history_triggered_at", "triggered_at.desc()"),
        Index("idx_alert_history_category", "category"),
        Index("idx_alert_history_severity", "severity"),
        Index("idx_alert_history_alert_name", "alert_name"),
        Index("idx_alert_history_tenant", "tenant"),
    )

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
    organization = Column(String(255), nullable=True)
    labels = Column(JSONB, nullable=True)
    annotations = Column(JSONB, nullable=True)
    fingerprint = Column(String(64), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AlertConfigAuditLog(Base):
    __tablename__ = "alert_config_audit_log"
    __table_args__ = (
        Index("idx_audit_log_organization", "organization"),
        Index("idx_audit_log_table_record", "table_name", "record_id"),
        Index("idx_audit_log_changed_at", "changed_at"),
        Index("idx_audit_log_changed_by", "changed_by"),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=True)
    table_name = Column(String(50), nullable=False)
    record_id = Column(Integer, nullable=False)
    operation = Column(String(20), nullable=False)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
    )
    before_values = Column(JSONB, nullable=True)
    after_values = Column(JSONB, nullable=True)
    change_description = Column(Text, nullable=True)

