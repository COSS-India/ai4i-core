"""seed_notification_catalog

Seeds the 7 notifications from the "Define Notifications" ticket into
configs_notification_alert. All 7 rows ship uniform — no recipient_roles,
no config — until an Adopter Admin configures them via a later ticket's
PATCH. Every row is a plain unconfigured catalog entry; there is no
auto-selected default here.

Kept as a separate revision from the DDL so the data can be rolled back and
re-applied without touching the table, matching this repo's existing seed
pattern (see 52eb3034332e_seed_inference_types.py).

Revision ID: 1d3f8e77bac4
Revises: b72ca7d83df6
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1d3f8e77bac4'
down_revision: Union[str, None] = 'b72ca7d83df6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, type, module)
_ROWS = [
    ("TIER_ASSIGNED", "NOTIFICATION", "TIER"),
    ("TIER_CHANGED", "NOTIFICATION", "TIER"),
    ("BUDGET_ASSIGNED", "NOTIFICATION", "BUDGET"),
    ("BUDGET_UPDATED", "NOTIFICATION", "BUDGET"),
    ("QUOTA_LIMIT_UPDATED", "NOTIFICATION", "QUOTA"),
    ("QUOTA_EXHAUSTED", "NOTIFICATION", "QUOTA"),
    ("BUDGET_EXHAUSTED", "NOTIFICATION", "BUDGET"),
]


def upgrade() -> None:
    rows = ",\n    ".join(
        f"('{name}', '{type_}', '{module}', '{{EMAIL}}')" for name, type_, module in _ROWS
    )
    op.execute(
        "INSERT INTO configs_notification_alert (name, type, module, channels) VALUES\n"
        f"    {rows}\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name, _, _ in _ROWS)
    # Targeted delete, never TRUNCATE — an operator may have added rows via
    # a future CRUD API and those are not this revision's to remove.
    op.execute(f"DELETE FROM configs_notification_alert WHERE name IN ({names});")
