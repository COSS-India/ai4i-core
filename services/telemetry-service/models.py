"""
SQLAlchemy models for telemetry_db.
"""
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class LogMetadata(Base):
    __tablename__ = "log_metadata"
    __table_args__ = (
        Index("idx_log_metadata_log_id", "log_id"),
        Index("idx_log_metadata_service_name", "service_name"),
        Index("idx_log_metadata_correlation_id", "correlation_id"),
        Index("idx_log_metadata_created_at", "created_at"),
        Index("idx_log_metadata_service_correlation", "service_name", "correlation_id"),
    )

    id = Column(Integer, primary_key=True)
    log_id = Column(String(255), unique=True, nullable=False)
    service_name = Column(String(100), nullable=False)
    environment = Column(String(50), nullable=False)
    log_level = Column(String(20), nullable=False)
    correlation_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class TraceMetadata(Base):
    __tablename__ = "trace_metadata"
    __table_args__ = (
        Index("idx_trace_metadata_trace_id", "trace_id"),
        Index("idx_trace_metadata_span_id", "span_id"),
        Index("idx_trace_metadata_parent_span_id", "parent_span_id"),
        Index("idx_trace_metadata_service_name", "service_name"),
        Index("idx_trace_metadata_created_at", "created_at"),
        Index("idx_trace_metadata_trace_span", "trace_id", "span_id"),
    )

    id = Column(Integer, primary_key=True)
    trace_id = Column(String(255), nullable=False)
    span_id = Column(String(255), nullable=False)
    parent_span_id = Column(String(255), nullable=True)
    service_name = Column(String(100), nullable=False)
    operation_name = Column(String(255), nullable=False)
    duration = Column(Numeric(10, 3), nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class EventCorrelation(Base):
    __tablename__ = "event_correlations"
    __table_args__ = (
        Index("idx_event_correlations_correlation_id", "correlation_id"),
        Index("idx_event_correlations_event_type", "event_type"),
        Index("idx_event_correlations_first_seen", "first_seen"),
        Index("idx_event_correlations_last_seen", "last_seen"),
    )

    id = Column(Integer, primary_key=True)
    correlation_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_count = Column(Integer, server_default="1", nullable=True)
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class DataEnrichmentRule(Base):
    __tablename__ = "data_enrichment_rules"
    __table_args__ = (
        Index("idx_data_enrichment_rules_rule_name", "rule_name"),
        Index("idx_data_enrichment_rules_active", "is_active"),
    )

    id = Column(Integer, primary_key=True)
    rule_name = Column(String(255), unique=True, nullable=False)
    source_field = Column(String(255), nullable=False)
    target_field = Column(String(255), nullable=False)
    enrichment_type = Column(String(50), nullable=False)
    configuration = Column(JSONB, nullable=False)
    is_active = Column(Boolean, server_default="true", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
