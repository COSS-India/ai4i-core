"""add inference_server_type and ssl_verify to services

Revision ID: c7e8f9a0b1c2
Revises: 265a08f8fbff
Create Date: 2026-04-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7e8f9a0b1c2"
down_revision: Union[str, None] = "265a08f8fbff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "services",
        sa.Column(
            "inference_server_type",
            sa.String(length=32),
            nullable=False,
            server_default="triton",
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "ssl_verify",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.create_check_constraint(
        "ck_services_inference_server_type",
        "services",
        "inference_server_type IN ('triton', 'http')",
    )
    op.execute(
        """
        DO $$
        DECLARE
          updated_count integer;
        BEGIN
          UPDATE services s
          SET inference_server_type = 'http'
          FROM models m
          WHERE s.model_id = m.model_id
            AND s.model_version = m.version
            AND m.task->>'type' = 'llm';

          GET DIAGNOSTICS updated_count = ROW_COUNT;
          RAISE NOTICE 'Backfilled inference_server_type=http for % services rows (llm models)', updated_count;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_services_inference_server_type", "services", type_="check")
    op.drop_column("services", "ssl_verify")
    op.drop_column("services", "inference_server_type")
