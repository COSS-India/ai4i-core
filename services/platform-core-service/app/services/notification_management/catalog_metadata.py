"""Code-side display metadata for the notification catalog.

Display name, description and detail-line format string are deliberately not
columns on configs_notification_alert (see the design's "What is
deliberately not on the catalog row"): they are developer-configured, not
Adopter-editable, so keeping them in code means the catalog PATCH surface
can never touch them.

Copy for the 7 NOTIFICATION-type rows is taken verbatim from the "Define
Notifications" ticket: description from its Trigger column, detail_line
from its Notification Details column (placeholders renamed to the field
names the payload/context actually uses). Copy for the 2 ALERT-type rows
(QUOTA_THRESHOLD, BUDGET_THRESHOLD) follows the "Define Alerts" ticket and
the design's section 6.3 payload-keys table the same way. Copy for the 5
MONITORING-type rows follows the "Define Monitoring Alerts" ticket / design.

Not shared via libs/ai4i_core: that package is pulled from PyPI in both
services' requirements.txt (not an editable/local install), so landing this
there would need a version bump and publish this ticket doesn't require —
auth-service's email templates (a later ticket) don't consume this module
yet. Revisit consolidating the two if/when that ticket needs the same
strings auth-service renders from.
"""

from dataclasses import dataclass

from app.schemas.enums.notification_management import NotificationName, NotificationModule


@dataclass(frozen=True)
class NotificationMetadata:
    display_name: str
    description: str
    module: NotificationModule
    detail_line: str


NOTIFICATION_METADATA: dict[NotificationName, NotificationMetadata] = {
    NotificationName.TIER_ASSIGNED: NotificationMetadata(
        display_name="Tier Assigned",
        description="Fires when the Adopter Admin assigns a Tier to a tenant for the first time.",
        module=NotificationModule.TIER,
        detail_line="Tier: {tier_name}",
    ),
    NotificationName.TIER_CHANGED: NotificationMetadata(
        display_name="Tier Reassigned",
        description="Fires when the Adopter Admin moves a tenant from one Tier to a different Tier.",
        module=NotificationModule.TIER,
        detail_line="Tier changed from {previous} to {current}",
    ),
    NotificationName.BUDGET_ASSIGNED: NotificationMetadata(
        display_name="Budget Assigned",
        description="Fires when the Adopter Admin assigns a Budget to a tenant for the first time.",
        module=NotificationModule.BUDGET,
        detail_line="Budget: {current}",
    ),
    NotificationName.BUDGET_UPDATED: NotificationMetadata(
        display_name="Budget Revised",
        description="Fires when the Adopter Admin changes an existing Budget amount for a tenant.",
        module=NotificationModule.BUDGET,
        detail_line="Budget changed from {previous} to {current}",
    ),
    NotificationName.QUOTA_LIMIT_UPDATED: NotificationMetadata(
        display_name="Quota Limit Updated",
        description="Fires when the Adopter Admin changes a Quota limit for a tenant's task type.",
        module=NotificationModule.QUOTA,
        detail_line="Quota for {inference_name} changed from {previous} to {current}",
    ),
    NotificationName.QUOTA_EXHAUSTED: NotificationMetadata(
        display_name="Quota Exhausted",
        description="Fires when a tenant's Quota reaches 100% and new requests are blocked.",
        module=NotificationModule.QUOTA,
        detail_line=(
            "Quota for {inference_name} of {limit} fully consumed. "
            "Resets at the start of next month."
        ),
    ),
    NotificationName.BUDGET_EXHAUSTED: NotificationMetadata(
        display_name="Budget Exhausted",
        description="Fires when a tenant's Budget is fully depleted and new requests are blocked.",
        module=NotificationModule.BUDGET,
        detail_line=(
            "Budget of {limit} fully consumed. "
            "Remains exhausted until revised by your Adopter Admin."
        ),
    ),
    # ── ALERT-type rows (the alert catalog) ──
    NotificationName.QUOTA_THRESHOLD: NotificationMetadata(
        display_name="Quota Threshold",
        description=(
            "Fires when a tenant's Quota usage crosses one of its configured "
            "percentage thresholds."
        ),
        module=NotificationModule.QUOTA,
        detail_line="{inference_name} quota at {percent}% ({observed} of {limit})",
    ),
    NotificationName.BUDGET_THRESHOLD: NotificationMetadata(
        display_name="Budget Threshold",
        description=(
            "Fires when a tenant's Budget usage crosses one of its configured "
            "percentage thresholds."
        ),
        module=NotificationModule.BUDGET,
        detail_line="Budget at {percent}% ({observed} of {limit})",
    ),
    # ── MONITORING-type rows (the monitoring alert catalog) ──
    NotificationName.ERROR_RATE_4XX: NotificationMetadata(
        display_name="4xx Error Rate",
        description="Fires when 4xx error rate crosses the configured threshold.",
        module=NotificationModule.MONITORING,
        detail_line="4xx Error Rate at {observed}% (threshold {threshold}%)",
    ),
    NotificationName.ERROR_RATE_5XX: NotificationMetadata(
        display_name="5xx Error Rate",
        description="Fires when 5xx error rate crosses the configured threshold.",
        module=NotificationModule.MONITORING,
        detail_line="5xx Error Rate at {observed}% (threshold {threshold}%)",
    ),
    NotificationName.LATENCY_P50: NotificationMetadata(
        display_name="P50 Latency",
        description="Fires when P50 latency crosses the configured threshold.",
        module=NotificationModule.MONITORING,
        detail_line="P50 Latency at {observed}s (threshold {threshold}s)",
    ),
    NotificationName.LATENCY_P95: NotificationMetadata(
        display_name="P95 Latency",
        description="Fires when P95 latency crosses the configured threshold.",
        module=NotificationModule.MONITORING,
        detail_line="P95 Latency at {observed}s (threshold {threshold}s)",
    ),
    NotificationName.LATENCY_P99: NotificationMetadata(
        display_name="P99 Latency",
        description="Fires when P99 latency crosses the configured threshold.",
        module=NotificationModule.MONITORING,
        detail_line="P99 Latency at {observed}s (threshold {threshold}s)",
    ),
}


# ── Catalog PATCH validation (code-side, per the design's 6.1 "Legal
# recipient roles per notification" table) ──

#: Legal ``recipient_roles`` keys per catalog name. The 9 NOTIFICATION and
#: ALERT rows are restricted to ADMIN / TENANT ADMIN. Gate 4 of the send
#: gate validates against this at runtime; the catalog PATCH enforces the
#: same set on write, per the design ("Enforced by the API"). The 5
#: MONITORING rows follow their own recipient model: Adopter Admin and/or
#: Moderator ("Define Monitoring Alerts" ticket).
_ADMIN_AND_TENANT_ADMIN = frozenset({"TENANT ADMIN", "ADMIN"})
_ADMIN_AND_MODERATOR = frozenset({"ADMIN", "MODERATOR"})

MONITORING_ALERT_NAMES = frozenset({
    NotificationName.ERROR_RATE_4XX,
    NotificationName.ERROR_RATE_5XX,
    NotificationName.LATENCY_P50,
    NotificationName.LATENCY_P95,
    NotificationName.LATENCY_P99,
})

LEGAL_RECIPIENT_ROLES: dict[NotificationName, frozenset[str]] = {
    name: _ADMIN_AND_MODERATOR if name in MONITORING_ALERT_NAMES else _ADMIN_AND_TENANT_ADMIN
    for name in NotificationName
}

#: ``thresholds`` bands: whole percents 1-99, exactly 3 bands (no more, no
#: fewer) — e.g. a "low"/"warning"/"critical" style set an Adopter Admin
#: names and sets a percentage/active flag for, without the band itself
#: carrying a name. Not expressible as a column CHECK (a count across a
#: JSONB array is not one) — service-enforced, per the design.
MIN_THRESHOLD_PERCENT = 1
MAX_THRESHOLD_PERCENT = 99
THRESHOLD_BAND_COUNT = 3
