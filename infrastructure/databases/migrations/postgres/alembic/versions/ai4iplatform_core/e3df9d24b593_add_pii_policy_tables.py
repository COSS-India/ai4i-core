"""add pii policy tables

Creates the PII policy data model: category, sub_category, policy_type,
policy and audit_log.

The companion column applications.policy_id lives in the auth DB and is
added by ai4iplatform_auth/51379ee0d696_add_policy_id_to_applications.py.

Postgres has no foreign keys on array elements, so policy.policy_type_id
(-> policy_type.id) and audit_log.policy_id (-> policy.id) are not enforced
by the database; the application layer must validate them.

Revision ID: e3df9d24b593
Revises: 7a3c9e1f5b2d
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3df9d24b593"
down_revision: Union[str, None] = "7a3c9e1f5b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUARDRAIL_SCOPE_ENUM = "guardrail_scope_enum"
_GUARDRAIL_SCOPE_VALUES = ["input", "output", "both"]


def upgrade() -> None:
    bind = op.get_bind()
    # Create the enum once here; column references use create_type=False so
    # create_table() does not emit a second CREATE TYPE.
    postgresql.ENUM(*_GUARDRAIL_SCOPE_VALUES, name=GUARDRAIL_SCOPE_ENUM).create(bind, checkfirst=True)
    guardrail_scope_enum = postgresql.ENUM(
        *_GUARDRAIL_SCOPE_VALUES, name=GUARDRAIL_SCOPE_ENUM, create_type=False
    )

    op.create_table(
        "category",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("name", name="uq_category_name"),
    )

    op.create_table(
        "sub_category",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(
            ["category_id"], ["category.id"], name="fk_sub_category_category_id", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("name", name="uq_sub_category_name"),
    )
    op.create_index("ix_sub_category_category_id", "sub_category", ["category_id"])

    op.create_table(
        "policy_type",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_type", sa.String(100), nullable=False),
        sa.Column(
            "policy_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.UniqueConstraint("policy_type", name="uq_policy_type_policy_type"),
    )

    op.create_table(
        "policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("guardrail_scope", guardrail_scope_enum, nullable=False),
        sa.Column("is_global", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("sub_category_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("policy_type_id", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.ForeignKeyConstraint(
            ["sub_category_id"], ["sub_category.id"], name="fk_policy_sub_category_id", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("policy_id", name="uq_policy_policy_id"),
        sa.UniqueConstraint("name", name="uq_policy_name"),
    )
    op.create_index("ix_policy_sub_category_id", "policy", ["sub_category_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_id", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("model_request", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("guardrail_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_audit_log_trace_id", "audit_log", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_trace_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_policy_sub_category_id", table_name="policy")
    op.drop_table("policy")
    op.drop_table("policy_type")
    op.drop_index("ix_sub_category_category_id", table_name="sub_category")
    op.drop_table("sub_category")
    op.drop_table("category")
    postgresql.ENUM(name=GUARDRAIL_SCOPE_ENUM).drop(op.get_bind(), checkfirst=True)
