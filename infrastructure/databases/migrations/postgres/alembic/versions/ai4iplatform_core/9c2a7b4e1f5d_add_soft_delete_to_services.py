"""add_soft_delete_to_services

Revision ID: 9c2a7b4e1f5d
Revises: 31d7bc3f4379, 961e254313e2
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c2a7b4e1f5d'
down_revision: Union[str, Sequence[str]] = ['31d7bc3f4379', '961e254313e2']
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col["name"] for col in inspector.get_columns("mm_services")]

    # Add deleted_at column if it doesn't already exist
    if "deleted_at" not in existing_columns:
        op.add_column(
            "mm_services",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Create index on deleted_at for query performance
    op.create_index(
        "ix_mm_services_deleted_at",
        "mm_services",
        ["deleted_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_mm_services_deleted_at", table_name="mm_services", if_exists=True)
    op.drop_column("mm_services", "deleted_at")
