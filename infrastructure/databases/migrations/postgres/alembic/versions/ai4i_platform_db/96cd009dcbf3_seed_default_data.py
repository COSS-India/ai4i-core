"""seed_default_data

Revision ID: 96cd009dcbf3
Revises: 1136a6462a4d
Create Date: 2026-05-18 15:50:03.048242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96cd009dcbf3'
down_revision: Union[str, None] = '1136a6462a4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
