"""Alert-management ORM models — share platform-core's Base.

Tables live in `ai4iplatform_core` (per migration plan); the alert feature
no longer has its own `alerting_db`. All classes register with the shared
`app.models.Base` so Alembic autogenerate picks them up.
"""

from app.models.alert_management.alert_definition import AlertAnnotation, AlertDefinition
from app.models.alert_management.alert_history import AlertHistory
from app.models.alert_management.notification_receiver import NotificationReceiver
from app.models.alert_management.routing_rule import RoutingRule

__all__ = [
    "AlertAnnotation",
    "AlertDefinition",
    "AlertHistory",
    "NotificationReceiver",
    "RoutingRule",
]
