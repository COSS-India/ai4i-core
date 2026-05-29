"""ORM models for `alert_definitions` and `alert_annotations`.

The two are kept in one module because `AlertAnnotation` is FK-bound to
`AlertDefinition` and has no independent meaning. Lifted verbatim from
alert-management-service/models.py:31-108 with two deliberate changes:

  - `organization` column dropped (org-extraction logic removed per plan).
  - Per-organization indexes that referenced the dropped column are also
    dropped.
"""

from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.models import Base


class AlertDefinition(Base):
    __tablename__ = "alert_definitions"
    __table_args__ = (
        UniqueConstraint("name", name="unique_alert_name"),
        Index("idx_alert_definitions_enabled", "enabled"),
        Index("idx_alert_definitions_category", "category"),
        Index("idx_alert_definitions_severity", "severity"),
    )

    id = Column(Integer, primary_key=True)
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
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())

    annotations = relationship(
        "AlertAnnotation",
        back_populates="alert_definition",
        cascade="all, delete-orphan",
    )


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
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())

    alert_definition = relationship("AlertDefinition", back_populates="annotations")
