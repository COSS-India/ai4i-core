"""
SQLAlchemy models for alerting_db.
"""
from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        Index("idx_alert_rules_name", "name"),
        Index("idx_alert_rules_metric_name", "metric_name"),
        Index("idx_alert_rules_active", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    metric_name = Column(String(255), nullable=False)
    threshold = Column(Numeric(15, 6), nullable=False)
    operator = Column(String(10), nullable=False)
    severity = Column(String(20), nullable=False)
    evaluation_window = Column(Integer, server_default="300", nullable=True)
    notification_channels = Column(ARRAY(Text), nullable=True)
    is_active = Column(Boolean, server_default="true", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_rule_id", "rule_id"),
        Index("idx_alerts_status", "status"),
        Index("idx_alerts_fired_at", "fired_at"),
        Index("idx_alerts_metric_name", "metric_name"),
        Index("idx_alerts_rule_status", "rule_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    rule_id = Column(Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=True)
    metric_name = Column(String(255), nullable=False)
    current_value = Column(Numeric(15, 6), nullable=False)
    threshold = Column(Numeric(15, 6), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(20), server_default="firing", nullable=True)
    fired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)


class NotificationHistory(Base):
    __tablename__ = "notification_history"
    __table_args__ = (
        Index("idx_notification_history_alert_id", "alert_id"),
        Index("idx_notification_history_sent_at", "sent_at"),
        Index("idx_notification_history_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True)
    channel = Column(String(50), nullable=False)
    recipient = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)


class EscalationPolicy(Base):
    __tablename__ = "escalation_policies"
    __table_args__ = (Index("idx_escalation_policies_name", "name"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    rules = Column(JSONB, nullable=False)
    schedule = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class AnomalyDetectionModel(Base):
    __tablename__ = "anomaly_detection_models"
    __table_args__ = (
        Index("idx_anomaly_models_metric_name", "metric_name"),
        Index("idx_anomaly_models_active", "is_active"),
        Index("idx_anomaly_models_last_trained", "last_trained_at"),
    )

    id = Column(Integer, primary_key=True)
    metric_name = Column(String(255), nullable=False)
    model_type = Column(String(50), nullable=False)
    model_parameters = Column(JSONB, nullable=False)
    training_data_size = Column(Integer, nullable=False)
    last_trained_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    accuracy_score = Column(Numeric(5, 4), nullable=True)
    is_active = Column(Boolean, server_default="true", nullable=True)


class AlertDefinition(Base):
    __tablename__ = "alert_definitions"
    __table_args__ = (
        UniqueConstraint("organization", "name", name="unique_organization_alert_name"),
        Index("idx_alert_definitions_organization", "organization"),
        Index("idx_alert_definitions_enabled", "enabled"),
        Index("idx_alert_definitions_category", "category"),
        Index("idx_alert_definitions_severity", "severity"),
        Index("idx_alert_definitions_organization_enabled", "organization", "enabled"),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    promql_expr = Column(Text, nullable=False)
    category = Column(String(50), server_default="application", nullable=False)
    severity = Column(String(20), nullable=False)
    urgency = Column(String(20), server_default="medium", nullable=True)
    alert_type = Column(String(50), nullable=True)
    scope = Column(String(50), nullable=True)
    evaluation_interval = Column(String(20), server_default="30s", nullable=True)
    for_duration = Column(String(20), server_default="5m", nullable=True)
    enabled = Column(Boolean, server_default="true", nullable=True)
    threshold_value = Column(Numeric(asdecimal=False), nullable=True)
    threshold_unit = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)


class AlertAnnotation(Base):
    __tablename__ = "alert_annotations"
    __table_args__ = (
        UniqueConstraint("alert_definition_id", "annotation_key", name="unique_alert_annotation_key"),
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class NotificationReceiver(Base):
    __tablename__ = "notification_receivers"
    __table_args__ = (
        UniqueConstraint("organization", "receiver_name", name="unique_organization_receiver_name"),
        Index("idx_notification_receivers_organization", "organization"),
        Index("idx_notification_receivers_enabled", "enabled"),
    )

    id = Column(Integer, primary_key=True)
    organization = Column(String(100), nullable=False)
    receiver_name = Column(String(255), nullable=False)
    email_to = Column(ARRAY(Text), nullable=False)
    email_subject_template = Column(Text, nullable=True)
    email_body_template = Column(Text, nullable=True)
    enabled = Column(Boolean, server_default="true", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)


class RoutingRule(Base):
    __tablename__ = "routing_rules"
    __table_args__ = (
        UniqueConstraint("organization", "rule_name", name="unique_organization_rule_name"),
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
    receiver_id = Column(Integer, ForeignKey("notification_receivers.id", ondelete="CASCADE"), nullable=False)
    match_severity = Column(String(20), nullable=True)
    match_category = Column(String(50), nullable=True)
    match_alert_type = Column(String(50), nullable=True)
    group_by = Column(ARRAY(Text), nullable=True)
    group_wait = Column(String(20), server_default="10s", nullable=True)
    group_interval = Column(String(20), server_default="10s", nullable=True)
    repeat_interval = Column(String(20), server_default="12h", nullable=True)
    continue_routing = Column(Boolean, server_default="false", nullable=True)
    priority = Column(Integer, server_default="100", nullable=True)
    enabled = Column(Boolean, server_default="true", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)


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
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    before_values = Column(JSONB, nullable=True)
    after_values = Column(JSONB, nullable=True)
    change_description = Column(Text, nullable=True)
