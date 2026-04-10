"""create policy-service tables

Revision ID: 0001_policy_service
Revises: 
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_policy_service"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pii_policy",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_global", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "supported_languages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("policy_id"),
    )
    op.create_index(op.f("ix_pii_policy_name"), "pii_policy", ["name"], unique=True)

    op.create_table(
        "pii_types",
        sa.Column("pii_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pii_type_label", sa.String(length=255), nullable=False),
        sa.Column("regex_pattern", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("mask_format", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("pii_type_id"),
        sa.UniqueConstraint("pii_type_label", name="uq_pii_type_label"),
    )
    op.create_index(op.f("ix_pii_types_pii_type_label"), "pii_types", ["pii_type_label"], unique=False)

    op.create_table(
        "policy_pii_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pii_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pii_type_id"], ["pii_types.pii_type_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["pii_policy.policy_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "pii_type_id", name="uq_policy_pii_type"),
    )
    op.create_index(op.f("ix_policy_pii_types_pii_type_id"), "policy_pii_types", ["pii_type_id"], unique=False)
    op.create_index(op.f("ix_policy_pii_types_policy_id"), "policy_pii_types", ["policy_id"], unique=False)

    op.create_table(
        "tenant_policy",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["pii_policy.policy_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "policy_id", name="uq_tenant_policy"),
    )
    op.create_index(op.f("ix_tenant_policy_policy_id"), "tenant_policy", ["policy_id"], unique=False)
    op.create_index(op.f("ix_tenant_policy_tenant_id"), "tenant_policy", ["tenant_id"], unique=False)

    op.create_table(
        "pii_audit_logs",
        sa.Column("pii_audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_context", sa.String(length=255), nullable=True),
        sa.Column("pii_count", sa.Integer(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["pii_policy.policy_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("pii_audit_id"),
    )
    op.create_index(op.f("ix_pii_audit_logs_policy_id"), "pii_audit_logs", ["policy_id"], unique=False)
    op.create_index(op.f("ix_pii_audit_logs_tenant_id"), "pii_audit_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_pii_audit_logs_trace_id"), "pii_audit_logs", ["trace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pii_audit_logs_trace_id"), table_name="pii_audit_logs")
    op.drop_index(op.f("ix_pii_audit_logs_tenant_id"), table_name="pii_audit_logs")
    op.drop_index(op.f("ix_pii_audit_logs_policy_id"), table_name="pii_audit_logs")
    op.drop_table("pii_audit_logs")

    op.drop_index(op.f("ix_tenant_policy_tenant_id"), table_name="tenant_policy")
    op.drop_index(op.f("ix_tenant_policy_policy_id"), table_name="tenant_policy")
    op.drop_table("tenant_policy")

    op.drop_index(op.f("ix_policy_pii_types_policy_id"), table_name="policy_pii_types")
    op.drop_index(op.f("ix_policy_pii_types_pii_type_id"), table_name="policy_pii_types")
    op.drop_table("policy_pii_types")

    op.drop_index(op.f("ix_pii_types_pii_type_label"), table_name="pii_types")
    op.drop_table("pii_types")

    op.drop_index(op.f("ix_pii_policy_name"), table_name="pii_policy")
    op.drop_table("pii_policy")

