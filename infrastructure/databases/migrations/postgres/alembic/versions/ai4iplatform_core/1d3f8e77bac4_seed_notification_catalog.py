"""seed_notification_catalog

Seeds the 7 notifications from the "Define Notifications" ticket into
configs_notification_alert. TIER_ASSIGNED and TIER_CHANGED ship pre-enabled
with TENANT ADMIN as their recipient role — the only two notifications the
Portal currently lets an Adopter Admin toggle Tenant Admin on at all (every
other row's legal-roles set is ADMIN-only, enforced in code, not the DB).
The remaining 5 rows stay is_enabled=false / config='{}' until an Adopter
Admin configures them via a later ticket's PATCH.

Kept as a separate revision from the DDL so the data can be rolled back and
re-applied without touching the table, matching this repo's existing seed
pattern (see 52eb3034332e_seed_inference_types.py).

Revision ID: 1d3f8e77bac4
Revises: b72ca7d83df6
Create Date: 2026-09-09 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1d3f8e77bac4'
down_revision: Union[str, None] = 'b72ca7d83df6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (name, type, module, is_enabled, config)
_ROWS = [
    (
        "TIER_ASSIGNED", "NOTIFICATION", "TIER", True,
        {"recipient_roles": {"TENANT ADMIN": True}},
    ),
    (
        "TIER_CHANGED", "NOTIFICATION", "TIER", True,
        {"recipient_roles": {"TENANT ADMIN": True}},
    ),
    ("BUDGET_ASSIGNED", "NOTIFICATION", "BUDGET", False, {}),
    ("BUDGET_UPDATED", "NOTIFICATION", "BUDGET", False, {}),
    ("QUOTA_LIMIT_UPDATED", "NOTIFICATION", "QUOTA", False, {}),
    ("QUOTA_EXHAUSTED", "NOTIFICATION", "QUOTA", False, {}),
    ("BUDGET_EXHAUSTED", "NOTIFICATION", "BUDGET", False, {}),
]


def upgrade() -> None:
    rows = ",\n    ".join(
        "('{name}', '{type_}', '{module}', '{{EMAIL}}', {enabled}, '{config}'::jsonb)".format(
            name=name,
            type_=type_,
            module=module,
            enabled="true" if is_enabled else "false",
            config=json.dumps(config).replace("'", "''"),
        )
        for name, type_, module, is_enabled, config in _ROWS
    )
    op.execute(
        "INSERT INTO configs_notification_alert (name, type, module, channels, is_enabled, config) VALUES\n"
        f"    {rows}\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name, _, _, _, _ in _ROWS)
    # Targeted delete, never TRUNCATE — an operator may have added rows via
    # a future CRUD API and those are not this revision's to remove.
    op.execute(f"DELETE FROM configs_notification_alert WHERE name IN ({names});")
