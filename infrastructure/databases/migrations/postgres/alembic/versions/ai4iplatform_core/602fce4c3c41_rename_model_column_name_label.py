"""rename model-column 'name' label to 'Model Name'

The model-column config row seeded in a3c5e7f9b1d4 labels the 'name' field
as just "Name". This renames that label to "Model Name" to match what the
model list UI column actually represents.

This row has been editable via PUT /config/{id} since release-2.11, so
admins may have already changed labels, reordered entries, or tweaked
other fields on deployed environments. upgrade()/downgrade() therefore
only rewrite the single array element whose key is 'name' and whose label
still matches the expected before/after value, leaving every other entry
(and its position) untouched. If an admin has already changed the 'name'
label away from "Name", upgrade() is a no-op for that row; likewise
downgrade() is a no-op if the label is no longer "Model Name".

Revision ID: 602fce4c3c41
Revises: fb79c598fb1b
Create Date: 2026-11-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "602fce4c3c41"
down_revision: Union[str, None] = "fb79c598fb1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MODEL_COLUMN_TYPE = "model-column"

_RELABEL_SQL = """
    UPDATE configs c
    SET data = (
        SELECT jsonb_agg(
            CASE WHEN e->>'key' = 'name' AND e->>'label' = :old_label
                 THEN jsonb_set(e, '{label}', to_jsonb(CAST(:new_label AS text)))
                 ELSE e END
            ORDER BY i
        )
        FROM jsonb_array_elements(c.data) WITH ORDINALITY AS t(e, i)
    )
    WHERE c.type = :t
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(_RELABEL_SQL),
        {"t": _MODEL_COLUMN_TYPE, "old_label": "Name", "new_label": "Model Name"},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(_RELABEL_SQL),
        {"t": _MODEL_COLUMN_TYPE, "old_label": "Model Name", "new_label": "Name"},
    )
