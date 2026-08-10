"""add_ulca_inference_endpoint_fields_to_mm_services

AI4IDS-2710: aligns mm_services with ULCA's InferenceAPIEndPoint schema
(deployment-service-specs.yml). Adds the fields that had no home on Service
before:

- inference_api_key (JSONB {name, value}) — new canonical shape for the auth
  header. The existing `api_key` column (plain string) is left untouched and
  unread-by-new-code; it stays only as a deprecated legacy value, no dual
  write, no backfill.
- inference_schema (JSONB) — ULCA's `schema` (InferenceSchemaArray). Required
  at the API layer (ServiceCreateRequest) on new creates; nullable here since
  existing rows have none and are never backfilled.
- is_sync_api (Boolean) / async_api_details (JSONB) — Service now owns its
  own copy of these rather than inheriting the linked Model's, since sync-
  vs-async is a property of a specific deployment, not the model artifact.
- is_multilingual_enabled (Boolean, default false), supported_input_formats
  (JSONB), supported_output_formats (JSONB), provider_name (String 100),
  inference_model_id (String 100) — net-new ULCA fields with no prior
  ai4i-core equivalent.

All nullable/defaulted so existing rows are unaffected; nothing here is
backfilled.

Revision ID: a7c9e1f3b5d7
Revises: f2a4c6e8b0d2
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7c9e1f3b5d7'
down_revision: Union[str, None] = 'f2a4c6e8b0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

_NEW_COLUMNS = [
    ("inference_api_key", postgresql.JSONB(), True, None),
    ("inference_schema", postgresql.JSONB(), True, None),
    ("is_sync_api", sa.Boolean(), True, None),
    ("async_api_details", postgresql.JSONB(), True, None),
    ("is_multilingual_enabled", sa.Boolean(), False, sa.false()),
    ("supported_input_formats", postgresql.JSONB(), True, None),
    ("supported_output_formats", postgresql.JSONB(), True, None),
    ("provider_name", sa.String(100), True, None),
    ("inference_model_id", sa.String(100), True, None),
]


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_services")}

    for name, col_type, nullable, server_default in _NEW_COLUMNS:
        if name not in existing_columns:
            op.add_column(
                "mm_services",
                sa.Column(name, col_type, nullable=nullable, server_default=server_default),
            )

    # Drop the server default now that existing rows are backfilled to
    # `false` — the ORM model only declares a Python-side default (mirrors
    # is_try_it_default's f4a6c8e0b2d4/f2a4c6e8b0d2 history), so leaving it
    # here would just make `alembic revision --autogenerate` flag drift.
    if "is_multilingual_enabled" not in existing_columns:
        op.alter_column("mm_services", "is_multilingual_enabled", server_default=None)


def downgrade() -> None:
    for name, _, _, _ in reversed(_NEW_COLUMNS):
        op.drop_column("mm_services", name)
