"""add rate_limit to tiers

Revision ID: 7a3c9e1f5b2d
Revises: 1d4e6a8c0f2b
Create Date: 2026-10-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7a3c9e1f5b2d"
down_revision: Union[str, None] = "1d4e6a8c0f2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHECK_NAME = "ck_tiers_rate_limit_positive"


def upgrade() -> None:
    op.add_column("tiers", sa.Column("rate_limit", sa.Integer(), nullable=True))
    op.create_check_constraint(_CHECK_NAME, "tiers", "rate_limit > 0")


def downgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "tiers", type_="check")
    op.drop_column("tiers", "rate_limit")
