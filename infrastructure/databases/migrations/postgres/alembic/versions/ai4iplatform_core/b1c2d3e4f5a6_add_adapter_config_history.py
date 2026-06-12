"""add_adapter_config_history

Revision ID: b1c2d3e4f5a6
Revises: d7b2c4e6f8a1
Create Date: 2026-06-12 00:00:00.000000

Creates mm_models_adapter_config_history, the durable backup of each model's
v1 adapter_config before it is migrated to the v2 (JSONata) schema
(AI4IDS-1981). Per-model v2 migrations snapshot the old config here first, so a
rollback can restore it without redeploying. This table is intentionally NOT
dropped by the later v1-removal cleanup; it is the permanent rollback record.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "d7b2c4e6f8a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "mm_models_adapter_config_history" in inspector.get_table_names():
        return
    op.create_table(
        "mm_models_adapter_config_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_id", sa.String(255), nullable=False),
        sa.Column("version", sa.String(100), nullable=True),
        sa.Column("schema_version", sa.String(20), nullable=True),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_mm_models_adapter_config_history_model_id",
        "mm_models_adapter_config_history",
        ["model_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mm_models_adapter_config_history_model_id",
        table_name="mm_models_adapter_config_history",
    )
    op.drop_table("mm_models_adapter_config_history")
