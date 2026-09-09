"""Code-side display metadata for the notification catalog.

Display name, description and detail-line format string are deliberately not
columns on configs_notification_alert (see the design's "What is
deliberately not on the catalog row"): they are developer-configured, not
Adopter-editable, so keeping them in code means the catalog PATCH surface
can never touch them.

Copy is taken verbatim from the "Define Notifications" ticket: description
from its Trigger column, detail_line from its Notification Details column
(placeholders renamed to the field names the payload/context actually uses).

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
}
