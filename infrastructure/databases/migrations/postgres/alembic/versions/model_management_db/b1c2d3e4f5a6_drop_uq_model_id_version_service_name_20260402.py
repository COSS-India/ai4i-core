"""b1c2d3e4f5a6_drop_uq_model_id_version_service_name_20260402

Revision ID: b1c2d3e4f5a6
Revises: a4b5c6d7e8f9
Create Date: 2026-04-02
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_model_id_version_service_name",
        "services",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_model_id_version_service_name",
        "services",
        ["model_id", "model_version", "name"],
    )

