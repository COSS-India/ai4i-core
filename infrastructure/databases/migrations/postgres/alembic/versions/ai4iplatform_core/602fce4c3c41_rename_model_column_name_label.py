"""rename model-column 'name' label to 'Model Name'

The model-column config row seeded in a3c5e7f9b1d4 labels the 'name' field
as just "Name". This renames that label to "Model Name" to match what the
model list UI column actually represents. No other fields in the row are
changed.

Only the data column is updated; id, is_default, created_by/at and
updated_by/at are left untouched.

This row is editable via PUT /config/{id}. upgrade() and downgrade()
overwrite configs.data unconditionally, so any manual edit made between
this migration running and a later downgrade (or re-run) is replaced by
the hardcoded value below, not preserved or restored.

Revision ID: 602fce4c3c41
Revises: fb79c598fb1b
Create Date: 2026-11-19

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "602fce4c3c41"
down_revision: Union[str, None] = "fb79c598fb1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MODEL_COLUMN_TYPE = "model-column"

_OLD_MODEL_COLUMN_DATA = [
    {"key": "name", "label": "Name", "required": True},
    {"key": "version", "label": "Version", "required": True},
    {"key": "taskType", "label": "Task Type", "required": True},
    {"key": "providerName", "label": "Provider Name", "required": True},
    {"key": "status", "label": "Status", "required": False},
    {"key": "createdAt", "label": "Created At", "required": False},
    {"key": "noOfServices", "label": "No. of Services", "required": False},
    {"key": "actions", "label": "Actions", "required": True},
]

_NEW_MODEL_COLUMN_DATA = [
    {"key": "name", "label": "Model Name", "required": True},
    {"key": "version", "label": "Version", "required": True},
    {"key": "taskType", "label": "Task Type", "required": True},
    {"key": "providerName", "label": "Provider Name", "required": True},
    {"key": "status", "label": "Status", "required": False},
    {"key": "createdAt", "label": "Created At", "required": False},
    {"key": "noOfServices", "label": "No. of Services", "required": False},
    {"key": "actions", "label": "Actions", "required": True},
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _MODEL_COLUMN_TYPE, "d": json.dumps(_NEW_MODEL_COLUMN_DATA)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE configs SET data = CAST(:d AS jsonb) WHERE type = :t"),
        {"t": _MODEL_COLUMN_TYPE, "d": json.dumps(_OLD_MODEL_COLUMN_DATA)},
    )
