"""add_ulca_model_fields

Adds the Model Registry columns needed to align mm_models with the ULCA
model-schema.yml spec: trainingDataset (required per ULCA), plus
isLangDetectionEnabled / isMultilingual / licenseUrl (optional per ULCA).

Existing rows are backfilled with the same defaults new rows get
(training_dataset={}, booleans=false), so the NOT NULL constraints on
training_dataset/is_lang_detection_enabled/is_multilingual can be applied
without a separate data migration. Enforcement of a real (non-empty)
trainingDataset on new writes happens at the Pydantic layer, not the DB.

Revision ID: a3b5c7d9e1f2
Revises: c8d9e0f1a2b3
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a3b5c7d9e1f2'
down_revision: Union[str, None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = {col["name"] for col in inspector.get_columns("mm_models")}

    if "is_lang_detection_enabled" not in existing_columns:
        op.add_column(
            "mm_models",
            sa.Column(
                "is_lang_detection_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if "is_multilingual" not in existing_columns:
        op.add_column(
            "mm_models",
            sa.Column(
                "is_multilingual",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if "license_url" not in existing_columns:
        op.add_column(
            "mm_models",
            sa.Column("license_url", sa.String(length=500), nullable=True),
        )

    if "training_dataset" not in existing_columns:
        op.add_column(
            "mm_models",
            sa.Column(
                "training_dataset",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    # Drop the server defaults now that existing rows are backfilled — the
    # ORM model only declares Python-side defaults (matching every other
    # JSONB/boolean column on this table), so leaving them here would just
    # make `alembic revision --autogenerate` flag a spurious drift forever.
    op.alter_column("mm_models", "is_lang_detection_enabled", server_default=None)
    op.alter_column("mm_models", "is_multilingual", server_default=None)
    op.alter_column("mm_models", "training_dataset", server_default=None)


def downgrade() -> None:
    op.drop_column("mm_models", "training_dataset")
    op.drop_column("mm_models", "license_url")
    op.drop_column("mm_models", "is_multilingual")
    op.drop_column("mm_models", "is_lang_detection_enabled")
