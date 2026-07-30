"""widen_mm_services_service_id

Schema-only change, no data touched: widens mm_services.service_id from
VARCHAR(255) to VARCHAR(500), matching mm_services.endpoint's existing cap
in the same table. Replaces b6f4c9a2e7d1_backfill_human_readable_service_ids
(dropped per review — that migration rewrote every existing service_id,
which is the live routing key inference-service resolves from the OpenAI
`model` field and the pay-per-use consumer prices on; regenerating it would
break every existing client integration and silently drop billing for
in-flight requests).

No existing service_id is touched here. Going forward, new service_ids are
already whatever the caller supplies via POST /services — `serviceId` is a
required field with no hash-based fallback (see
app/schemas/model_management/service.py, `validate_service_id` /
SERVICE_ID_MAX_LEN, bumped to 500 to match). The only ever
non-human-readable service_ids were produced by the one-time
seed_default_data / seed_adapter_configs_and_endpoints migrations
(`_generate_service_id` = sha256(name)[:32]) — a bootstrap step, not part of
the live create-service path. This migration just removes any concern about
future descriptive service_ids being truncated; it does not backfill or
regenerate existing values.

Revision ID: c7d2f5a9e3b6
Revises: a3b5c7d9e1f2
Create Date: 2026-07-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d2f5a9e3b6"
down_revision: Union[str, None] = "a3b5c7d9e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "mm_services",
        "service_id",
        existing_type=sa.String(length=255),
        type_=sa.String(length=500),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "mm_services",
        "service_id",
        existing_type=sa.String(length=500),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
