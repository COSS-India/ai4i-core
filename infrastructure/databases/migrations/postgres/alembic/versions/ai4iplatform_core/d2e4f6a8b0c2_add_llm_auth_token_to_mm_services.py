"""add_llm_auth_token_to_mm_services

Adds `llm_auth_token` (nullable Text) to mm_services — the optional vLLM
Authentication Token for LLM task-type services, stored encrypted at rest
(see app/core/service_credentials_crypto.py). A new column rather than the
pre-existing `api_key`/`inference_api_key`, since those are read unencrypted
and left unmasked in API responses for the Triton flow's sake.

Nullable, no default: existing rows are unaffected, nothing is backfilled.

Revision ID: d2e4f6a8b0c2
Revises: bcdd3516d0ab
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd2e4f6a8b0c2'
down_revision: Union[str, None] = 'bcdd3516d0ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_services")}

    if "llm_auth_token" not in existing_columns:
        op.add_column(
            "mm_services",
            sa.Column("llm_auth_token", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_services")}

    if "llm_auth_token" in existing_columns:
        op.drop_column("mm_services", "llm_auth_token")
