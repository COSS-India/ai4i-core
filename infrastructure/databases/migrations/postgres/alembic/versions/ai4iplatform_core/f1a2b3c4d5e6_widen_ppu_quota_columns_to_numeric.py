"""widen_ppu_quota_columns_to_numeric

Widens ppu_quota_usage.units_used, ppu_quota_usage.monthly_quota_snap, and
ppu_tier_quotas.monthly_quota from BigInteger to Numeric(15, 6).

Minute-billed inference types (asr, speaker-diarization, language-diarization,
audio-lang-detection) now bill fractional minutes instead of rounding up to a
1-minute floor (see span_attributes._count_audio_tokens), so these columns
must hold fractional values.

Revision ID: f1a2b3c4d5e6
Revises: d4e6f8a1b3c5
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd4e6f8a1b3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'ppu_quota_usage', 'units_used',
        type_=sa.Numeric(15, 6),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default='0',
    )
    op.alter_column(
        'ppu_quota_usage', 'monthly_quota_snap',
        type_=sa.Numeric(15, 6),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        'ppu_tier_quotas', 'monthly_quota',
        type_=sa.Numeric(15, 6),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'ppu_tier_quotas', 'monthly_quota',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 6),
        existing_nullable=False,
    )
    op.alter_column(
        'ppu_quota_usage', 'monthly_quota_snap',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 6),
        existing_nullable=True,
    )
    op.alter_column(
        'ppu_quota_usage', 'units_used',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 6),
        existing_nullable=False,
        existing_server_default='0',
    )
