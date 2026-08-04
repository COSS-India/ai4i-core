"""add_expected_response_schema_to_mm_services

Adds mm_services.expected_response_schema (JSONB) — a sample of a correct
response for the service's endpoint, supplied by the admin at creation time.
Endpoint validation (app/utils/endpoint_validator.py) probes the endpoint
with a task-type-appropriate sample request and structurally compares the
actual response against this schema, rejecting the service if it doesn't
match (AI4IDS-1844).

Nullable at the DB level since existing rows predate this feature; the API
layer (ServiceCreateRequest) enforces it as required on create.

Revision ID: c6e8a0b2d4f6
Revises: f4a6c8e0b2d4
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c6e8a0b2d4f6'
down_revision: Union[str, None] = 'f4a6c8e0b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_services")}

    if "expected_response_schema" not in existing_columns:
        op.add_column(
            "mm_services",
            sa.Column("expected_response_schema", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("mm_services", "expected_response_schema")
