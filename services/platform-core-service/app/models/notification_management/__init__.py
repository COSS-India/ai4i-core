"""Notification-management ORM models — share platform-core's Base.

Tables live in ai4iplatform_core.
"""

from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.models.notification_management.ledger_notification_alert import (
    LedgerNotificationAlert,
)
from app.models.notification_management.notification_alert_failure_log import (
    NotificationAlertFailureLog,
)
from app.models.notification_management.notification_alert_threshold import (
    NotificationAlertThreshold,
)
from app.models.notification_management.tenant_notification_subscription import (
    TenantNotificationSubscription,
)

__all__ = [
    "ConfigNotificationAlert",
    "LedgerNotificationAlert",
    "NotificationAlertFailureLog",
    "NotificationAlertThreshold",
    "TenantNotificationSubscription",
]
