"""drop unique constraint on policy_type.policy_type

Revision ID: a1b3c5d7e9f2
Revises: a9d4f2b6c8e1
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b3c5d7e9f2"
down_revision: Union[str, None] = "a9d4f2b6c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_policy_type_policy_type", "policy_type", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_policy_type_policy_type", "policy_type", ["policy_type"])
