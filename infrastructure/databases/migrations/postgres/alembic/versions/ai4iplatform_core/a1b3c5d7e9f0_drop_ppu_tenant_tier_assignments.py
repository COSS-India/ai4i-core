"""drop ppu_tenant_tier_assignments

Revision ID: a1b3c5d7e9f0
Revises: 021f3168f9c8
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b3c5d7e9f0"
down_revision: Union[str, None] = "7986f2b0a159"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_ppu_tenant_tier_assignments_tenant_effective", table_name="ppu_tenant_tier_assignments")
    op.drop_index("ix_ppu_tenant_tier_assignments_effective_window", table_name="ppu_tenant_tier_assignments")
    op.drop_index("ix_ppu_tenant_tier_assignments_tier_id", table_name="ppu_tenant_tier_assignments")
    op.drop_table("ppu_tenant_tier_assignments")


def downgrade() -> None:
    op.create_table(
        "ppu_tenant_tier_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_limit", sa.Numeric(precision=15, scale=8), nullable=False),
        sa.Column("available_balance", sa.Numeric(precision=15, scale=8), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tier_id"], ["tiers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ppu_tenant_tier_assignments_tier_id", "ppu_tenant_tier_assignments", ["tier_id"])
    op.create_index("ix_ppu_tenant_tier_assignments_effective_window", "ppu_tenant_tier_assignments", ["effective_from", "effective_to"])
    op.create_index("ix_ppu_tenant_tier_assignments_tenant_effective", "ppu_tenant_tier_assignments", ["tenant_id", "effective_from", "effective_to"])
