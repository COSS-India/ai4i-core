"""add daily_usage.source

Revision ID: a1c3e5f7b9d2
Revises: a9d4f2b6c8e1
Create Date: 2026-10-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "a9d4f2b6c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "daily_usage_source_enum"
_ENUM_VALUES = ("rollup", "backfill")


def upgrade() -> None:
    sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME).create(op.get_bind(), checkfirst=True)
    op.add_column(
        "daily_usage",
        sa.Column(
            "source",
            sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME, create_type=False),
            nullable=False,
            server_default="rollup",
        ),
    )


def downgrade() -> None:
    op.drop_column("daily_usage", "source")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
