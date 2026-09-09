"""Notification-management ORM models — share platform-core's Base.

Tables live in ai4iplatform_core. Distinct from app.models.alert_management,
which is an unrelated Prometheus-style alerting feature (AlertDefinition,
RoutingRule, ...).
"""

from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)

__all__ = [
    "ConfigNotificationAlert",
]
