"""backfill_human_readable_service_ids

Regenerates mm_services.service_id for every row into a human-readable,
lowercase hyphenated slug derived from mm_services.name (e.g. "MH Gemma 32B"
-> "mh-gemma-32b"). Previous values were not reliably readable — some rows
(seeded via a1f2e3d4c5b6_seed_adapter_configs_and_endpoints.py and
d3e850228f7e_seed_default_data.py) hold a 32-char SHA-256 hash of the name,
never a display-friendly string.

service_id is the value clients send in the OpenAI `model` field, and the
grouping key for the model-consumption metering endpoint (see
model-consumption-api-highlevel-design.md), so it needs to stand on its own
as a readable label.

`model_id` is untouched — cardinality is unaffected: each service still maps
to exactly one model, and multiple services may still share the same
model_id (one model backing several deployed services).

Collisions (two rows slugifying to the same value) are resolved with a
`-2`, `-3`, ... suffix, preserving the unique constraint on service_id.

Revision ID: b6f4c9a2e7d1
Revises: a3b5c7d9e1f2
Create Date: 2026-07-30 00:00:00.000000

One-way migration: downgrade is intentionally unsupported. The prior
service_id values (including the opaque hashes above) are not preserved.
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6f4c9a2e7d1"
down_revision: Union[str, None] = "a3b5c7d9e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(name: str, fallback: str) -> str:
    """Lowercase, hyphen-separated slug — matches the existing entity-name
    pattern (`^[a-zA-Z0-9/-]+$`, see validate_entity_name in
    app/schemas/common.py)."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or fallback


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, name FROM mm_services ORDER BY created_at")
    ).fetchall()

    # Phase 1: move every row to a disjoint placeholder first. service_id has
    # a table-wide UNIQUE constraint enforced immediately (not deferred), so
    # writing final slugs directly could collide with another row's
    # not-yet-migrated (old) value mid-migration even though the final state
    # would be conflict-free. A placeholder guaranteed distinct from every
    # possible final slug removes that ordering hazard entirely.
    for row in rows:
        conn.execute(
            sa.text("UPDATE mm_services SET service_id = :tmp WHERE id = :id"),
            {"tmp": f"__migrating__{row.id}", "id": row.id},
        )

    # Phase 2: compute final slugs (unique among themselves) and write them.
    seen = set()
    for row in rows:
        base = _slugify(row.name, fallback=f"service-{str(row.id)[:8]}")
        candidate = base
        suffix = 2
        while candidate in seen:
            candidate = f"{base}-{suffix}"
            suffix += 1
        seen.add(candidate)

        conn.execute(
            sa.text("UPDATE mm_services SET service_id = :service_id WHERE id = :id"),
            {"service_id": candidate, "id": row.id},
        )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade is not supported: prior service_id values (including "
        "opaque SHA-256 hashes from earlier seed migrations) are not "
        "preserved. Restore from backup if rollback is required."
    )
