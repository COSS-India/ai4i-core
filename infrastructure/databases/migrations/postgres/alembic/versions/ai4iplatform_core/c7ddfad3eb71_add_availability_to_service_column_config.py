"""add availability to service column config

Adds an "availability" entry to the configs.data column list for
type='service-column', so the Service List UI can offer a model-availability
column backed by a live Prometheus "up" lookup. Non-sortable (the value
isn't stored, so there's nothing to ORDER BY on) and not visible by default.

Unlike b4d6f8a0c2e4, this migration does not overwrite configs.data
wholesale. It appends one element to the existing data->0->columns array
(and removes it on downgrade), so any other edits made to that row via
PUT /config/{id} — before or after this migration runs — are preserved.
upgrade() is idempotent: it only appends when no "availability" entry is
already present, so re-running it (or applying it to a row edited by hand to
already include one) is a no-op rather than a duplicate.

Revision ID: c7ddfad3eb71
Revises: ba861b49230d
Create Date: 2026-11-23

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7ddfad3eb71"
down_revision: Union[str, None] = "ba861b49230d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SERVICE_COLUMN_TYPE = "service-column"

_AVAILABILITY_COLUMN = {
    "id": "availability",
    "label": "Availability",
    "filter": None,
    "sortable": False,
    "mandatory": False,
    "filterable": False,
    "defaultVisible": False,
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE configs
            SET data = jsonb_set(
                data,
                '{0,columns}',
                (data #> '{0,columns}') || CAST(:col AS jsonb)
            )
            WHERE type = :t
              AND NOT EXISTS (
                  SELECT 1 FROM jsonb_array_elements(data #> '{0,columns}') elem
                  WHERE elem->>'id' = 'availability'
              )
            """
        ),
        {"t": _SERVICE_COLUMN_TYPE, "col": json.dumps([_AVAILABILITY_COLUMN])},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE configs
            SET data = jsonb_set(
                data,
                '{0,columns}',
                (
                    SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
                    FROM jsonb_array_elements(data #> '{0,columns}') elem
                    WHERE elem->>'id' != 'availability'
                )
            )
            WHERE type = :t
            """
        ),
        {"t": _SERVICE_COLUMN_TYPE},
    )
