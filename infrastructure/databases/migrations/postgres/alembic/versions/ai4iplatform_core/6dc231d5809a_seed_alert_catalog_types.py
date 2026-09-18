"""seed_alert_catalog_types

Seeds the 2 ALERT-type rows from the "Define Alerts" ticket into
configs_notification_alert: QUOTA_THRESHOLD and BUDGET_THRESHOLD. Both ship
with the ticket's threshold bands (50%, 75%, 90%) present as keys in
config.thresholds but unchecked (false) — the bands exist so an Adopter
Admin can toggle them on, not because any fire by default. Both ship with
no recipient_roles either — same as all 7 rows 1d3f8e77bac4 seeded, since no
shipped path resolves a default audience for either; an Adopter Admin picks
recipients and enables bands via the alert-catalog PATCH.

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


_DEFAULT_THRESHOLDS = {"thresholds": {"50": False, "75": False, "90": False}}

# (name, type, module, config)
_ROWS = [
    ("QUOTA_THRESHOLD", "ALERT", "QUOTA", _DEFAULT_THRESHOLDS),
    ("BUDGET_THRESHOLD", "ALERT", "BUDGET", _DEFAULT_THRESHOLDS),
]


def upgrade() -> None:
    rows = ",\n    ".join(
        "('{name}', '{type_}', '{module}', '{{EMAIL}}', '{config}'::jsonb)".format(
            name=name,
            type_=type_,
            module=module,
            config=json.dumps(config).replace("'", "''"),
        )
        for name, type_, module, config in _ROWS
    )
    op.execute(
        "INSERT INTO configs_notification_alert (name, type, module, channels, config) VALUES\n"
        f"    {rows}\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    names = ",".join(f"'{name}'" for name, _, _, _ in _ROWS)
    # Targeted delete, never TRUNCATE — an operator may have added rows via
    # a future CRUD API and those are not this revision's to remove.
    op.execute(f"DELETE FROM configs_notification_alert WHERE name IN ({names});")
