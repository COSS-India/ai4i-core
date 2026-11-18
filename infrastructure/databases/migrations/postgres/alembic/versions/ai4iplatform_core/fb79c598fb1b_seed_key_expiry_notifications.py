"""seed the GRACE_PERIOD_EXPIRING and API_KEY_EXPIRING catalog rows and their day thresholds

Revision ID: fb79c598fb1b
Revises: 23e621f010ba
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'fb79c598fb1b'
down_revision: Union[str, None] = '23e621f010ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMES = ("GRACE_PERIOD_EXPIRING", "API_KEY_EXPIRING")
# Days before expiry -> severity. Fixed for now (editable = false), as the
# fixed 100 % band of the EXHAUSTED rows.
_BANDS = ((10, "INFO"), (5, "WARNING"), (1, "CRITICAL"))


def upgrade() -> None:
    for name in _NAMES:
        op.execute(
            f"""
            INSERT INTO configs_notification_alert
                (name, type, module, channels, scope, recipient_roles)
            SELECT '{name}', 'NOTIFICATION', 'API_KEY', '{{EMAIL}}', 'GLOBAL',
                   '{{"ADMIN": true, "TENANT ADMIN": true}}'::jsonb
            WHERE NOT EXISTS (SELECT 1 FROM configs_notification_alert WHERE name = '{name}');
            """
        )
        for days, severity in _BANDS:
            op.execute(
                f"""
                INSERT INTO notification_alert_threshold
                    (notification_id, band_value, unit, severity, active, editable)
                SELECT id, {days}, 'DAYS', '{severity}', true, false
                  FROM configs_notification_alert
                 WHERE name = '{name}'
                ON CONFLICT (notification_id, band_value) DO NOTHING;
                """
            )


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name in _NAMES)
    # ledger_notification_alert's FK has no ON DELETE action; threshold and
    # subscription rows cascade.
    op.execute(
        "DELETE FROM ledger_notification_alert WHERE notification_id IN "
        f"(SELECT id FROM configs_notification_alert WHERE name IN ({names}));"
    )
    op.execute(f"DELETE FROM configs_notification_alert WHERE name IN ({names});")
