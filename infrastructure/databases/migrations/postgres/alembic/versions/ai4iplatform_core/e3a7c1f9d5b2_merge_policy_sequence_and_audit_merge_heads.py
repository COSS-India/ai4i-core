"""merge_policy_sequence_and_audit_merge_heads

9092247a3b27 (merge_usage_tables_and_policy_audit_heads, #1725) and
d1e3f5a7b9c2 (add_policy_id_seq sequence, policy-management branch) both
descend from different ancestors and landed in ai4iplatform_core as separate
heads, causing `alembic -x db=ai4iplatform_core upgrade head` to fail with
"Multiple head revisions are present" on any fresh DB or deploy.

The two branches touch unrelated objects (usage/policy-audit tables vs. the
policy_id_seq sequence), so their order doesn't matter. Pure merge, no DDL:
safe whichever branch a database has already applied.

Revision ID: e3a7c1f9d5b2
Revises: 9092247a3b27, d1e3f5a7b9c2
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'e3a7c1f9d5b2'
down_revision: Union[str, Sequence[str], None] = ('9092247a3b27', 'd1e3f5a7b9c2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
