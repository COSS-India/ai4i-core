"""Notification-catalog enums (name, type, module, channel).

Canonical sets for the ``configs_notification_alert`` table, mirroring the
column-level Postgres enums created in
b72ca7d83df6_create_notification_catalog_table. Kept as the schemas/enums
source of truth per this codebase's existing pattern (see
alert_management.py) — request/response schemas validate against these.
"""

from enum import Enum


class NotificationName(str, Enum):
    """The 9 names seeded across 1d3f8e77bac4_seed_notification_catalog (the
    7 NOTIFICATION-type rows) and add_alert_types_to_notification_catalog /
    seed_alert_catalog_types (the 2 ALERT-type rows: QUOTA_THRESHOLD,
    BUDGET_THRESHOLD — the standard alert catalog from the "Define Alerts"
    ticket)."""

    TIER_ASSIGNED = "TIER_ASSIGNED"
    TIER_CHANGED = "TIER_CHANGED"
    BUDGET_ASSIGNED = "BUDGET_ASSIGNED"
    BUDGET_UPDATED = "BUDGET_UPDATED"
    QUOTA_LIMIT_UPDATED = "QUOTA_LIMIT_UPDATED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    QUOTA_THRESHOLD = "QUOTA_THRESHOLD"
    BUDGET_THRESHOLD = "BUDGET_THRESHOLD"


class NotificationType(str, Enum):
    """The family a catalog row belongs to: the 7 notification-management
    rows are NOTIFICATION, the 2 alert-catalog rows (QUOTA_THRESHOLD,
    BUDGET_THRESHOLD) are ALERT. What the two catalog screens filter on."""

    NOTIFICATION = "NOTIFICATION"
    ALERT = "ALERT"


class NotificationModule(str, Enum):
    """Grouping and counting only — nothing reads this to decide behavior."""

    TIER = "TIER"
    BUDGET = "BUDGET"
    QUOTA = "QUOTA"


class NotificationChannel(str, Enum):
    """All four declared now so enabling one later is a seed update, not a
    schema change. Only EMAIL is used in v1."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    SLACK = "SLACK"
    WHATSAPP = "WHATSAPP"


VALID_NOTIFICATION_NAMES = {member.value for member in NotificationName}
VALID_NOTIFICATION_TYPES = {member.value for member in NotificationType}
VALID_NOTIFICATION_MODULES = {member.value for member in NotificationModule}
VALID_NOTIFICATION_CHANNELS = {member.value for member in NotificationChannel}
