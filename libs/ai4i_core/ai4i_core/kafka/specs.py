"""Fixed facts per notification type: dedup rule, subject keys, period key,
and whether a triggered row can RESET. Fixed in code, never stored in the DB.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .constants import DedupRule, NotificationName, NotificationType, SubjectKey


@dataclass(frozen=True)
class NotificationSpec:
    name: NotificationName
    notification_type: NotificationType
    dedup_rule: DedupRule
    subject_keys: Tuple[SubjectKey, ...]
    #: Subject key that makes each period its own ledger row, if any.
    period_key: Optional[SubjectKey] = None
    #: RESET applies: a triggered row re-arms once the value is below every
    #: band and the cooldown is over. Monitoring only.
    resets: bool = False
    #: tenant_id is always PLATFORM (no tenant).
    platform_scoped: bool = False

    @property
    def is_band(self) -> bool:
        return self.dedup_rule is DedupRule.BAND

    @property
    def is_state(self) -> bool:
        return self.dedup_rule is DedupRule.STATE


_NO_SUBJECT: Tuple[SubjectKey, ...] = ()
_QUOTA_SUBJECT = (SubjectKey.BILLING_MONTH, SubjectKey.MODEL_TASK_TYPE)
# budget_window (the tenant's current budget_effective_from/_to) makes a
# renewed or reactivated window its own ledger row, the same way
# billing_month gives quota a fresh one every month — otherwise a reset or
# renewal within the same window can never re-arm an already-triggered band.
_BUDGET_SUBJECT = (SubjectKey.BUDGET_CEILING, SubjectKey.BUDGET_WINDOW)
_MONITORING_SUBJECT = (SubjectKey.SERVICE_ID,)


def _state(name: NotificationName, subject_keys=_NO_SUBJECT) -> NotificationSpec:
    return NotificationSpec(name, NotificationType.NOTIFICATION, DedupRule.STATE, subject_keys)


def _usage(name: NotificationName, notification_type: NotificationType, subject_keys, period_key) -> NotificationSpec:
    return NotificationSpec(name, notification_type, DedupRule.BAND, subject_keys, period_key=period_key)


def _monitoring(name: NotificationName) -> NotificationSpec:
    return NotificationSpec(
        name, NotificationType.MONITORING, DedupRule.BAND, _MONITORING_SUBJECT,
        resets=True, platform_scoped=True,
    )


SPECS: Dict[NotificationName, NotificationSpec] = {
    spec.name: spec
    for spec in (
        _state(NotificationName.TIER_ASSIGNED),
        _state(NotificationName.TIER_CHANGED),
        _state(NotificationName.BUDGET_ASSIGNED),
        _state(NotificationName.BUDGET_UPDATED),
        _state(NotificationName.QUOTA_LIMIT_UPDATED, (SubjectKey.MODEL_TASK_TYPE,)),
        _usage(NotificationName.QUOTA_EXHAUSTED, NotificationType.NOTIFICATION, _QUOTA_SUBJECT, SubjectKey.BILLING_MONTH),
        _usage(NotificationName.BUDGET_EXHAUSTED, NotificationType.NOTIFICATION, _BUDGET_SUBJECT, SubjectKey.BUDGET_WINDOW),
        _usage(NotificationName.QUOTA_THRESHOLD, NotificationType.ALERT, _QUOTA_SUBJECT, SubjectKey.BILLING_MONTH),
        _usage(NotificationName.BUDGET_THRESHOLD, NotificationType.ALERT, _BUDGET_SUBJECT, SubjectKey.BUDGET_WINDOW),
        _monitoring(NotificationName.ERROR_RATE_4XX),
        _monitoring(NotificationName.ERROR_RATE_5XX),
        _monitoring(NotificationName.LATENCY_P50),
        _monitoring(NotificationName.LATENCY_P95),
        _monitoring(NotificationName.LATENCY_P99),
    )
}


def get_spec(name) -> Optional[NotificationSpec]:
    """Spec for a name (enum or string), or None for an unknown name."""
    try:
        return SPECS[NotificationName(name)]
    except ValueError:
        return None
