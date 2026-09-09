"""seed_alert_catalog_types

Seeds the 2 ALERT-type rows from the "Define Alerts" ticket into
configs_notification_alert: QUOTA_THRESHOLD and BUDGET_THRESHOLD. Both ship
with the ticket's default threshold bands (>=50%, >=75%, >=90%) preset in
config.thresholds, matching the acceptance criteria's table. Both ship
is_enabled=false / no recipient_roles key — same as 5 of the 7 rows
1d3f8e77bac4 seeded, since no shipped path resolves a default audience for
either the way QUOTA_LIMIT_UPDATED's TENANT ADMIN default is evidenced — an
Adopter Admin turns them on and picks recipients via the alert-catalog PATCH.

Kept as its own revision, after b83dc4f704d2's enum values, for the same
reason 1d3f8e77bac4 was split from b72ca7d83df6: separable rollback, and a
just-added enum value can't be used in the same transaction that added it.

Revision ID: 6dc231d5809a
Revises: b83dc4f704d2
Create Date: 2026-09-09 00:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6dc231d5809a'
down_revision: Union[str, None] = 'b83dc4f704d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_THRESHOLDS = {"thresholds": {"50": True, "75": True, "90": True}}

# (name, type, module, is_enabled, config)
_ROWS = [
    ("QUOTA_THRESHOLD", "ALERT", "QUOTA", False, _DEFAULT_THRESHOLDS),
    ("BUDGET_THRESHOLD", "ALERT", "BUDGET", False, _DEFAULT_THRESHOLDS),
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
