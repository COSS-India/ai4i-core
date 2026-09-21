"""Notification-catalog enums (name, type, module, channel).

Canonical sets for the ``configs_notification_alert`` table, mirroring the
column-level Postgres enums created in
b72ca7d83df6_create_notification_catalog_table. Kept as the schemas/enums
source of truth per this codebase's existing pattern (see
alert_management.py) — request/response schemas validate against these.
"""

from enum import Enum

from ai4i_core.kafka import NotificationName, NotificationType, NotificationChannel

__all__ = [
    "NotificationName",
    "NotificationType",
    "NotificationModule",
    "NotificationChannel",
    "VALID_NOTIFICATION_NAMES",
    "VALID_NOTIFICATION_TYPES",
    "VALID_NOTIFICATION_MODULES",
    "VALID_NOTIFICATION_CHANNELS",
]


class NotificationModule(str, Enum):
    """Grouping and counting only — nothing reads this to decide behavior."""

    TIER = "TIER"
    BUDGET = "BUDGET"
    QUOTA = "QUOTA"


VALID_NOTIFICATION_NAMES = {member.value for member in NotificationName}
VALID_NOTIFICATION_TYPES = {member.value for member in NotificationType}
VALID_NOTIFICATION_MODULES = {member.value for member in NotificationModule}
VALID_NOTIFICATION_CHANNELS = {member.value for member in NotificationChannel}
