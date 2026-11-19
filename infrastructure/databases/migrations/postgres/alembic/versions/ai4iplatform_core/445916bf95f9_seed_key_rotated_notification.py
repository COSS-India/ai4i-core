"""seed the KEY_ROTATED notification catalog row

Revision ID: 445916bf95f9
Revises: 5611c5d7c73d
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = '445916bf95f9'
down_revision: Union[str, None] = '5611c5d7c73d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO configs_notification_alert
            (name, type, module, channels, scope, recipient_roles)
        SELECT 'KEY_ROTATED', 'NOTIFICATION', 'API_KEY', '{EMAIL}', 'GLOBAL',
               '{"ADMIN": false, "TENANT ADMIN": true}'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM configs_notification_alert WHERE name = 'KEY_ROTATED');
        """
    )


def downgrade() -> None:
    # ledger_notification_alert's FK has no ON DELETE action; subscription rows cascade.
    op.execute(
        "DELETE FROM ledger_notification_alert WHERE notification_id IN "
        "(SELECT id FROM configs_notification_alert WHERE name = 'KEY_ROTATED');"
    )
    op.execute("DELETE FROM configs_notification_alert WHERE name = 'KEY_ROTATED';")
