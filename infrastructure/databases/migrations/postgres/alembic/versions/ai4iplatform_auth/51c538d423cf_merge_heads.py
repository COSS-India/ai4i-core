"""merge heads

Revision ID: 51c538d423cf
Revises: ba737c15e5ec, d6e7f8a9b1c2
Create Date: 2026-08-27 09:40:18.195473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51c538d423cf'
down_revision: Union[str, None] = ('ba737c15e5ec', 'd6e7f8a9b1c2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
