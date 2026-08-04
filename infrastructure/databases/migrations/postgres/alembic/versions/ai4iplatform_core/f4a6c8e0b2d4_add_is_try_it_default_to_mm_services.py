"""add_is_try_it_default_to_mm_services

Adds mm_services.is_try_it_default, an admin-settable flag marking which
published service the anonymous/no-login Try-It flow should use for a given
task_type. Replaces the previous frontend heuristic (lowest service_id
alphabetically), which had silently pinned Try-It to a broken service.

At most one service per task_type should have this flag set; enforcement of
that invariant lives in the service update path (app/services/model-management/
service_service.py), not the DB — mirrors how is_published's related
published_at/unpublished_at bookkeeping is also enforced at the service layer.

Revision ID: f4a6c8e0b2d4
Revises: a3b5c7d9e1f2
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f4a6c8e0b2d4'
down_revision: Union[str, None] = 'a3b5c7d9e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_services")}

    if "is_try_it_default" not in existing_columns:
        op.add_column(
            "mm_services",
            sa.Column(
                "is_try_it_default",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        op.create_index(
            "ix_mm_services_is_try_it_default",
            "mm_services",
            ["is_try_it_default"],
        )

    # Drop the server default now that existing rows are backfilled — the ORM
    # model only declares a Python-side default, matching is_published on the
    # same table, so leaving it here would just make `alembic revision
    # --autogenerate` flag a spurious drift forever.
    op.alter_column("mm_services", "is_try_it_default", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_mm_services_is_try_it_default", table_name="mm_services")
    op.drop_column("mm_services", "is_try_it_default")
