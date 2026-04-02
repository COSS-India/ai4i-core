"""a4b5c6d7e8f9_add_service_name_unique_constraint_20260402

Revision ID: a4b5c6d7e8f9
Revises: 500e60023e47
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "500e60023e47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_service_name", "services", ["name"])


def downgrade() -> None:
    op.drop_constraint("uq_service_name", "services", type_="unique")

