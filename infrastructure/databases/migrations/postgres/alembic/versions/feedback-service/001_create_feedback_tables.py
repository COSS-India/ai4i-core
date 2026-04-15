"""create feedback_metrics table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "feedback_metrics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Multi-tenancy
        sa.Column("organization", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),

        # Trace & service identification
        sa.Column("trace_id", sa.String(255), nullable=False, unique=True),
        sa.Column("service_id", sa.String(100), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("language", sa.String(50), nullable=True),

        # Content
        sa.Column("source_input", sa.Text, nullable=False),
        sa.Column("model_output", sa.Text, nullable=False),
        sa.Column("human_correction", sa.Text, nullable=True),

        # Explicit feedback
        sa.Column("feedback_source", sa.String(50), nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),

        # Implicit telemetry
        sa.Column("implicit_score", sa.Integer, nullable=True, server_default="0"),
        sa.Column("event_log", JSONB, nullable=True, server_default="'[]'::jsonb"),

        # AI evaluation
        sa.Column("ai_status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("payload", JSONB, nullable=True, server_default="'{}'::jsonb"),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Indices
    op.create_index("ix_feedback_organization", "feedback_metrics", ["organization"])
    op.create_index("ix_feedback_tenant_id", "feedback_metrics", ["tenant_id"])
    op.create_index("ix_feedback_trace_id", "feedback_metrics", ["trace_id"], unique=True)
    op.create_index("ix_feedback_service_id", "feedback_metrics", ["service_id"])
    op.create_index("ix_feedback_language", "feedback_metrics", ["language"])
    op.create_index("ix_feedback_created_at", "feedback_metrics", ["created_at"])
    op.create_index("ix_feedback_org_status", "feedback_metrics", ["organization", "ai_status"])
    op.create_index("ix_feedback_org_task", "feedback_metrics", ["organization", "task_type"])


def downgrade():
    op.drop_index("ix_feedback_org_task", table_name="feedback_metrics")
    op.drop_index("ix_feedback_org_status", table_name="feedback_metrics")
    op.drop_index("ix_feedback_created_at", table_name="feedback_metrics")
    op.drop_index("ix_feedback_language", table_name="feedback_metrics")
    op.drop_index("ix_feedback_service_id", table_name="feedback_metrics")
    op.drop_index("ix_feedback_trace_id", table_name="feedback_metrics")
    op.drop_index("ix_feedback_tenant_id", table_name="feedback_metrics")
    op.drop_index("ix_feedback_organization", table_name="feedback_metrics")
    op.drop_table("feedback_metrics")
