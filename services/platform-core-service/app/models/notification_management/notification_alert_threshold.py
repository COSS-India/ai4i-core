from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import func

from app.models import Base
from app.schemas.enums.notification_management import VALID_SEVERITIES, VALID_THRESHOLD_UNITS

_UNIT_ENUM = ENUM(*sorted(VALID_THRESHOLD_UNITS), name="notification_threshold_unit_enum", create_type=False)
_SEVERITY_ENUM = ENUM(*sorted(VALID_SEVERITIES), name="notification_severity_enum", create_type=False)


class NotificationAlertThreshold(Base):
    """One threshold band of a BAND-rule catalog row (QUOTA/BUDGET
    THRESHOLD and EXHAUSTED, and the 5 MONITORING rows).

    ``severity`` is counted from the top of the row's ladder (highest
    CRITICAL, second WARNING, rest INFO) and set by the API, never by an
    admin. ``editable = false`` marks the fixed 100 % band of the two
    EXHAUSTED rows, which the catalog PATCH never touches.
    """

    __tablename__ = "notification_alert_threshold"
    __table_args__ = (
        UniqueConstraint("notification_id", "band_value", name="uq_notification_alert_threshold_band"),
        CheckConstraint("band_value > 0", name="ck_notification_alert_threshold_positive"),
        CheckConstraint("unit <> 'PERCENT' OR band_value <= 100", name="ck_notification_alert_threshold_percent"),
        Index(
            "ix_notification_alert_threshold_active", "notification_id", postgresql_where=text("active")
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    notification_id = Column(
        BigInteger,
        ForeignKey(
            "configs_notification_alert.id",
            name="fk_notification_alert_threshold_notification_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    band_value = Column(Numeric(12, 4), nullable=False)
    unit = Column(_UNIT_ENUM, nullable=False)
    severity = Column(_SEVERITY_ENUM, nullable=False)
    active = Column(Boolean, nullable=False, server_default="false")
    editable = Column(Boolean, nullable=False, server_default="true")
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
