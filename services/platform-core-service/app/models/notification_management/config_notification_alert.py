from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.sql import func

from app.models import Base
from app.schemas.enums.notification_management import (
    VALID_NOTIFICATION_CHANNELS,
    VALID_NOTIFICATION_MODULES,
    VALID_NOTIFICATION_NAMES,
    VALID_NOTIFICATION_SCOPES,
    VALID_NOTIFICATION_TYPES,
)

_NAME_ENUM = ENUM(*VALID_NOTIFICATION_NAMES, name="notification_alert_name_enum", create_type=False)
_TYPE_ENUM = ENUM(*VALID_NOTIFICATION_TYPES, name="notification_alert_type_enum", create_type=False)
_MODULE_ENUM = ENUM(*VALID_NOTIFICATION_MODULES, name="notification_alert_module_enum", create_type=False)
_CHANNEL_ENUM = ENUM(*VALID_NOTIFICATION_CHANNELS, name="notification_alert_channel_enum", create_type=False)
_SCOPE_ENUM = ENUM(*VALID_NOTIFICATION_SCOPES, name="notification_alert_scope_enum", create_type=False)


class ConfigNotificationAlert(Base):
    """The notification/alert catalog — one row per notification type.

    The API only ever updates these rows (never inserts or deletes).
    ``scope`` decides who a row applies to: GLOBAL is platform-wide with no
    per-institution opt-out; INSTITUTION is available for an institution to
    subscribe to via ``tenant_notification_subscription``. ``config`` holds
    only ``thresholds`` (ALERT-type rows). Everything listed, counted or
    grouped by the catalog UI is a column: name, type, module, channels,
    scope. See catalog_metadata.py for the code-side display name,
    description and detail line that decorate these rows on read.
    """

    __tablename__ = "configs_notification_alert"
    __table_args__ = (
        UniqueConstraint("name", name="uq_configs_notification_alert_name"),
        CheckConstraint("cardinality(channels) > 0", name="ck_configs_notification_alert_channels"),
        Index("ix_configs_notification_alert_channels", "channels", postgresql_using="gin"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(_NAME_ENUM, nullable=False)
    type = Column(_TYPE_ENUM, nullable=False)
    module = Column(_MODULE_ENUM, nullable=False)
    channels = Column(ARRAY(_CHANNEL_ENUM), nullable=False, server_default="{EMAIL}")
    scope = Column(_SCOPE_ENUM, nullable=False, server_default="GLOBAL")
    config = Column(JSONB, nullable=False, server_default="{}")
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by = Column(String(255), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
