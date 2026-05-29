"""Alert-management domain services.

Folder name is hyphenated per project convention. External callers must use
`importlib.import_module("app.services.alert-management.<module>")`; the
relative imports below work fine because Python resolves them via the loaded
package object, not the dotted name.
"""

from .definition_service import AlertDefinitionService
from .history_service import AlertHistoryService
from .receiver_service import NotificationReceiverService
from .routing_rule_service import RoutingRuleService
from .sync_service import SyncService

__all__ = [
    "AlertDefinitionService",
    "AlertHistoryService",
    "NotificationReceiverService",
    "RoutingRuleService",
    "SyncService",
]
