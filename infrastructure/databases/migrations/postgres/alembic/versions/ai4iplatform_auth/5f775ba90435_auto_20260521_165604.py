"""No-op: redundant tenants.status autogenerate (chain head before dd4ab7 removal)

Revision ID: 5f775ba90435
Revises: 53a41e6233f1
Create Date: 2026-05-21 11:26:05.859320

Autogenerate duplicate — no schema change.

Real tenants.status work lives in **c4e8f1a2b3d0** (earlier in this branch, not in the same PR
file list): migrates labels to PENDING/ACTIVE/… and sets DEFAULT 'PENDING'.

Chain slice:
  … → c4e8f1a2b3d0 (tenant status enum + default)
    → aca4be0874b3 (no-op, same autogenerate noise)
    → 53a41e6233f1 (users.creation_type_enum + tenant label)
    → 5f775ba90435 (this file, no-op)

See MIGRATION_CHAIN.md in this folder for the full ordered list.
"""
from typing import Sequence, Union

revision: str = '5f775ba90435'
down_revision: Union[str, None] = '53a41e6233f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
