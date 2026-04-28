"""widen_token_verification_token_to_text

Revision ID: fa6fd0aca3a2
Revises: 03c373bdd881
Create Date: 2026-04-27 11:04:26.692317

No-op: token_verification.token is created as TEXT in the initial migration (03c373bdd881).
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'fa6fd0aca3a2'
down_revision: Union[str, None] = '03c373bdd881'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
