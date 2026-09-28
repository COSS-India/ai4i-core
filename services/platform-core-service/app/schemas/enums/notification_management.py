"""Notification-catalog enums (name, type, module, channel, scope, unit,
severity).

The canonical members live in the shared ai4i_core.kafka constants, so every
producer and this service use the same values; request/response schemas
validate against them. They mirror the column-level Postgres enums of the
configs_notification_alert and notification_alert_threshold tables.
"""

from ai4i_core.kafka import (
    NotificationChannel,
    NotificationModule,
    NotificationName,
    NotificationScope,
    NotificationType,
    Severity,
    ThresholdUnit,
)

#: Unit of a MONITORING row's threshold band: error rates are a percentage
#: of requests, latencies are seconds.
MonitoringThresholdUnit = ThresholdUnit

__all__ = [
    "NotificationName",
    "NotificationType",
    "NotificationModule",
    "NotificationChannel",
    "NotificationScope",
    "ThresholdUnit",
    "MonitoringThresholdUnit",
    "Severity",
    "VALID_NOTIFICATION_NAMES",
    "VALID_NOTIFICATION_TYPES",
    "VALID_NOTIFICATION_MODULES",
    "VALID_NOTIFICATION_CHANNELS",
    "VALID_NOTIFICATION_SCOPES",
    "VALID_THRESHOLD_UNITS",
    "VALID_SEVERITIES",
]

VALID_NOTIFICATION_NAMES = {member.value for member in NotificationName}
VALID_NOTIFICATION_TYPES = {member.value for member in NotificationType}
VALID_NOTIFICATION_MODULES = {member.value for member in NotificationModule}
VALID_NOTIFICATION_CHANNELS = {member.value for member in NotificationChannel}
VALID_NOTIFICATION_SCOPES = {member.value for member in NotificationScope}
VALID_THRESHOLD_UNITS = {member.value for member in ThresholdUnit}
VALID_SEVERITIES = {member.value for member in Severity}
