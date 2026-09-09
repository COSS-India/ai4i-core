"""Notification-catalog enums (name, type, module, channel).

Canonical sets for the ``configs_notification_alert`` table, mirroring the
column-level Postgres enums created in
b72ca7d83df6_create_notification_catalog_table. Kept as the schemas/enums
source of truth per this codebase's existing pattern (see
alert_management.py) — request/response schemas validate against these.
"""

from enum import Enum


class NotificationName(str, Enum):
    """The 7 notifications seeded by 1d3f8e77bac4_seed_notification_catalog.

    Two ALERT-type values (QUOTA_THRESHOLD, BUDGET_THRESHOLD) exist in the
    wider Notifications and Alerts design but are out of this ticket's scope
    and are not seeded — adding them later is an additive
    ``ALTER TYPE ... ADD VALUE`` plus a seed migration, not a rewrite.
    """

    TIER_ASSIGNED = "TIER_ASSIGNED"
    TIER_CHANGED = "TIER_CHANGED"
    BUDGET_ASSIGNED = "BUDGET_ASSIGNED"
    BUDGET_UPDATED = "BUDGET_UPDATED"
    QUOTA_LIMIT_UPDATED = "QUOTA_LIMIT_UPDATED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class NotificationType(str, Enum):
    """The family a catalog row belongs to. Every row seeded by this ticket
    is NOTIFICATION; ALERT is declared for the enum's full, reviewed domain."""

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
