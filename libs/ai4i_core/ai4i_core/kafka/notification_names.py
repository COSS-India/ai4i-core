"""Canonical notification/event names for configs_notification_alert.

The 9 names seeded across 1d3f8e77bac4_seed_notification_catalog (the 7
NOTIFICATION-type rows) and add_alert_types_to_notification_catalog /
seed_alert_catalog_types (the 2 ALERT-type rows: QUOTA_THRESHOLD,
BUDGET_THRESHOLD). Single source of truth so every producer/consumer
(auth-service, platform-core-service, kafka-consumers) references the same
values instead of re-typing the raw strings at each call site.
"""

from enum import Enum


class NotificationName(str, Enum):
    TIER_ASSIGNED = "TIER_ASSIGNED"
    TIER_CHANGED = "TIER_CHANGED"
    BUDGET_ASSIGNED = "BUDGET_ASSIGNED"
    BUDGET_UPDATED = "BUDGET_UPDATED"
    QUOTA_LIMIT_UPDATED = "QUOTA_LIMIT_UPDATED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    QUOTA_THRESHOLD = "QUOTA_THRESHOLD"
    BUDGET_THRESHOLD = "BUDGET_THRESHOLD"
