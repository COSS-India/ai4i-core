"""merge_usage_tables_and_policy_audit_heads

Both 3b5d7f9a1c2e (create_usage_events_table, the first of the
usage_events -> daily_usage -> LLM token prices chain ending at
5d7f9b1c3e4a, #1723) and c0d2e4f6a8b1 (add_audit_fields_to_policy_tables,
#1724) branch off f4a8c2d6e1b7. The two PRs were each single-headed on their
own and merged into release-2.9 one after the other, leaving
ai4iplatform_core with two heads, so a bare
`alembic -x db=ai4iplatform_core upgrade head` fails with "Multiple head
revisions are present".

The branches touch unrelated tables (usage_events, daily_usage, mm_services
vs. the policy tables), so their order doesn't matter. Pure merge, no DDL:
safe whichever branch a database has already applied.

Revision ID: 9092247a3b27
Revises: 5d7f9b1c3e4a, c0d2e4f6a8b1
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '9092247a3b27'
down_revision: Union[str, Sequence[str], None] = ('5d7f9b1c3e4a', 'c0d2e4f6a8b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
