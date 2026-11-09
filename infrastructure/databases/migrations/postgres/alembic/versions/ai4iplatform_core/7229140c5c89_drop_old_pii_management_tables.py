"""drop old pii-management tables

The pii-management module (app/models/pii_management/, app/services/pii-management/,
app/routes/pii.py) has been removed in favor of policy-management. Drops the
five pii_* tables it owned, created by b9e3f1a2c4d5_add_pii_tables_to_core_db.

Revision ID: 7229140c5c89
Revises: f1b2c3d4e5f6
Create Date: 2026-11-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7229140c5c89"
down_revision: Union[str, None] = "f1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pii_audit_logs")
    op.execute("DROP TABLE IF EXISTS pii_tenant_domain_map")
    op.execute("DROP TABLE IF EXISTS pii_geo_library")
    op.execute("DROP TABLE IF EXISTS pii_pattern_library")
    op.execute("DROP TABLE IF EXISTS pii_domain_policies")


def downgrade() -> None:
    op.create_table(
        "pii_domain_policies",
        sa.Column("domain_id", sa.String(50), primary_key=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp"), nullable=True),
    )

    op.create_table(
        "pii_pattern_library",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_label", sa.String(50), nullable=False),
        sa.Column("lang_code", sa.String(10), nullable=False),
        sa.Column("regex_pattern", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), server_default=sa.text("1.0"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.UniqueConstraint("entity_label", "lang_code", name="uq_pii_pattern_entity_lang"),
    )

    op.create_table(
        "pii_geo_library",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("term_text", sa.String(100), nullable=False),
        sa.Column("lang_code", sa.String(10), nullable=False),
        sa.Column("term_type", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True),
    )

    op.create_table(
        "pii_tenant_domain_map",
        sa.Column("tenant_id", sa.String(255), primary_key=True),
        sa.Column("domain_id", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("current_timestamp"), nullable=True),
    )

    op.create_table(
        "pii_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("tenant_id", sa.String(50), nullable=True),
        sa.Column("domain_id", sa.String(50), nullable=True),
        sa.Column("target_context", sa.String(20), nullable=True),
        sa.Column("pii_count", sa.Integer(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("current_timestamp"), nullable=True),
    )
