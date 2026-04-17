"""legacy_policy_service_bridge

Revision ID: 0001_policy_service
Revises:
Create Date: 2026-04-17 00:00:00.000000

Purpose:
- Preserve compatibility for legacy environments whose `alembic_version`
  references `0001_policy_service`.
- Provide a resolvable base revision so Alembic can traverse to newer
  policy-service revisions.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "0001_policy_service"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op bridge for legacy revision compatibility.
    pass


def downgrade() -> None:
    # No-op: this revision does not mutate schema.
    pass
