"""widen_ppu_quota_columns_to_numeric

Widens ppu_quota_usage.units_used, ppu_quota_usage.monthly_quota_snap,
ppu_tier_quotas.monthly_quota, and ppu_tier_quotas.pending_monthly_quota from
BigInteger to Numeric(15, 4).

Minute-billed inference types (asr, speaker-diarization, language-diarization,
audio-lang-detection) now bill fractional minutes instead of rounding up to a
1-minute floor (see span_attributes._count_audio_tokens), so these columns
must hold fractional values. Scale 4 (not 2) is used so sub-second audio isn't
lost: at scale 2 a clip under ~0.6s rounds to 0.00 minutes and bills no quota;
scale 4 gives ~0.006s granularity. pending_monthly_quota is widened alongside
monthly_quota because the edit-tier flow stages quota changes there and the
monthly cron promotes pending_monthly_quota -> monthly_quota; leaving it
BigInteger would truncate fractional staged quotas.

Revision ID: b7e2c9a4f1d3
Revises: f1a2b3c4d5e6
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7e2c9a4f1d3'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'ppu_quota_usage', 'units_used',
        type_=sa.Numeric(15, 4),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
        existing_server_default='0',
    )
    op.alter_column(
        'ppu_quota_usage', 'monthly_quota_snap',
        type_=sa.Numeric(15, 4),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        'ppu_tier_quotas', 'monthly_quota',
        type_=sa.Numeric(15, 4),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
    op.alter_column(
        'ppu_tier_quotas', 'pending_monthly_quota',
        type_=sa.Numeric(15, 4),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'ppu_tier_quotas', 'pending_monthly_quota',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 4),
        existing_nullable=True,
    )
    op.alter_column(
        'ppu_tier_quotas', 'monthly_quota',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 4),
        existing_nullable=False,
    )
    op.alter_column(
        'ppu_quota_usage', 'monthly_quota_snap',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 4),
        existing_nullable=True,
    )
    op.alter_column(
        'ppu_quota_usage', 'units_used',
        type_=sa.BigInteger(),
        existing_type=sa.Numeric(15, 4),
        existing_nullable=False,
        existing_server_default='0',
    )
