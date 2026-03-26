"""auto_20260325_071139

Revision ID: 4adb2b7dead2
Revises: a14826e332ff
Create Date: 2026-03-25 07:11:41.623226

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "4adb2b7dead2"
down_revision: Union[str, None] = "a14826e332ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Compatibility bridge revision:
    # a14826e332ff already creates telemetry tables.
    pass


def downgrade() -> None:
    pass
