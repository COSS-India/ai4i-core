"""seed default configs

Adds is_default to configs and seeds the five config types the UI needs to
function out of the box (domain, model-column, service-column,
suspend-reasons, deactivate-reasons). Rows seeded here are protected: the
DELETE /config/{id} endpoint refuses to delete a row with is_default=true.

Seeding is skipped per-type if a row with that type already exists, so
re-running upgrade() is safe.

Revision ID: a3c5e7f9b1d4
Revises: b7d3f1a9c2e5
Create Date: 2026-11-09

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d4"
down_revision: Union[str, None] = "b7d3f1a9c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED_CONFIGS = {
    "domain": [
        {"key": "general", "label": "General", "required": False},
        {"key": "news", "label": "News", "required": False},
        {"key": "education", "label": "Education", "required": False},
        {"key": "legal", "label": "Legal", "required": False},
        {"key": "government-press-release", "label": "Government Press Release", "required": False},
        {"key": "healthcare", "label": "Healthcare", "required": False},
        {"key": "agriculture", "label": "Agriculture", "required": False},
        {"key": "automobile", "label": "Automobile", "required": False},
        {"key": "tourism", "label": "Tourism", "required": False},
        {"key": "financial", "label": "Financial", "required": False},
        {"key": "movies", "label": "Movies", "required": False},
        {"key": "subtitles", "label": "Subtitles", "required": False},
        {"key": "sports", "label": "Sports", "required": False},
        {"key": "technology", "label": "Technology", "required": False},
        {"key": "lifestyle", "label": "Lifestyle", "required": False},
        {"key": "entertainment", "label": "Entertainment", "required": False},
        {"key": "art-and-culture", "label": "Art and Culture", "required": False},
        {"key": "parliamentary", "label": "Parliamentary", "required": False},
        {"key": "economy", "label": "Economy", "required": False},
        {"key": "history", "label": "History", "required": False},
        {"key": "philosophy", "label": "Philosophy", "required": False},
        {"key": "religion", "label": "Religion", "required": False},
        {"key": "national-security-and-defence", "label": "National Security and Defence", "required": False},
        {"key": "literature", "label": "Literature", "required": False},
        {"key": "geography", "label": "Geography", "required": False},
    ],
    "model-column": [
        {"key": "name", "label": "Name", "required": True},
        {"key": "version", "label": "Version", "required": True},
        {"key": "taskType", "label": "Task Type", "required": True},
        {"key": "providerName", "label": "Provider Name", "required": True},
        {"key": "status", "label": "Status", "required": False},
        {"key": "createdAt", "label": "Created At", "required": False},
        {"key": "noOfServices", "label": "No. of Services", "required": False},
        {"key": "actions", "label": "Actions", "required": True},
    ],
    "service-column": [
        {"key": "name", "label": "Name", "required": True},
        {"key": "modelTaskType", "label": "Model Task Type", "required": False},
        {"key": "tier", "label": "Tier", "required": False},
        {"key": "status", "label": "Status", "required": False},
        {"key": "createdAt", "label": "Created At", "required": False},
        {"key": "modelName", "label": "Model Name", "required": False},
        {"key": "serviceId", "label": "Service ID", "required": False},
        {"key": "inputPrice", "label": "Input Price", "required": False},
        {"key": "outputPrice", "label": "Output Price", "required": False},
        {"key": "cachedInputPrice", "label": "Cached Input Price", "required": False},
        {"key": "publishedOn", "label": "Published On", "required": False},
        {"key": "actions", "label": "Actions", "required": True},
    ],
    "suspend-reasons": [
        {"key": "security-concern-under-investigation", "label": "Security concern under investigation", "required": True},
        {"key": "suspected-policy-violation-under-review", "label": "Suspected policy violation, under review", "required": True},
        {"key": "agreement-renewal-pending", "label": "Agreement renewal pending", "required": True},
        {"key": "requested-by-the-institution", "label": "Requested by the Institution", "required": True},
        {"key": "other-remarks-mandatory", "label": "Other (remarks mandatory)", "required": True},
    ],
    "deactivate-reasons": [
        {"key": "agreement-or-engagement-ended", "label": "Agreement or engagement ended", "required": True},
        {"key": "confirmed-policy-violation", "label": "Confirmed policy violation", "required": True},
        {"key": "institution-closed-or-merged", "label": "Institution closed or merged", "required": True},
        {"key": "requested-by-the-institution", "label": "Requested by the Institution", "required": True},
        {"key": "other-remarks-mandatory", "label": "Other (remarks mandatory)", "required": True},
    ],
}


def upgrade() -> None:
    op.add_column(
        "configs",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    conn = op.get_bind()
    for config_type, items in _SEED_CONFIGS.items():
        exists = conn.execute(
            sa.text("SELECT 1 FROM configs WHERE type = :t"), {"t": config_type}
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO configs (type, data, is_default) "
                "VALUES (:t, CAST(:d AS jsonb), TRUE)"
            ),
            {"t": config_type, "d": json.dumps(items)},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for config_type in _SEED_CONFIGS:
        conn.execute(sa.text("DELETE FROM configs WHERE type = :t"), {"t": config_type})
    op.drop_column("configs", "is_default")
