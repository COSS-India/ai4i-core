"""widen user_sessions.ip_address for X-Forwarded-For chains

Revision ID: c4d5e6f70891
Revises: 198c0fd8d490
Create Date: 2026-04-08

IPv6 + proxy chain in X-Forwarded-For exceeds VARCHAR(45) and caused login 500s.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f70891"
down_revision: Union[str, None] = "198c0fd8d490"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_sessions",
        "ip_address",
        existing_type=sa.String(length=45),
        type_=sa.String(length=512),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "user_sessions",
        "ip_address",
        existing_type=sa.String(length=512),
        type_=sa.String(length=45),
        existing_nullable=True,
    )