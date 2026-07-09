"""merge_ppu_tier_heads

Merges the two heads created by d1e2f3a4b5c6 (PPU tier_id/cost_accum on
ppu_quota_usage) and 5c6faec0df77 (pending_monthly_quota on
ppu_tier_quotas), both of which branched off d4e6f8a1b3c5.

Revision ID: bee612249258
Revises: f1a2b3c4d5e6, 5c6faec0df77
Create Date: 2026-07-09 00:00:00.000000

"""
from typing import Sequence, Union

revision: str = 'bee612249258'
down_revision: Union[str, Sequence[str], None] = ['f1a2b3c4d5e6', '5c6faec0df77']
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
