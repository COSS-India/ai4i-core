"""merge_threshold_and_tiers_index_heads

Both a3f5c7e9b1d3 (threshold_config_as_band_list) and c1d2e3f4a5b6
(partial_unique_index_tiers_name_non_deleted) branch off 6dc231d5809a —
two independent, unrelated migrations landed on separate branches the same
day and neither ever got a merge revision reconciling them, leaving
ai4iplatform_core with two heads. That's what
`alembic -x db=ai4iplatform_core upgrade head` (bare, unqualified) has been
failing on with "Multiple head revisions are present" — reproduced both
locally on a fresh database and on the `dev` environment's migration job.

Pure merge, no DDL — reconciles the two branches back into a single head.

Revision ID: bcdd3516d0ab
Revises: a3f5c7e9b1d3, c1d2e3f4a5b6
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'bcdd3516d0ab'
down_revision: Union[str, Sequence[str], None] = ('a3f5c7e9b1d3', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
