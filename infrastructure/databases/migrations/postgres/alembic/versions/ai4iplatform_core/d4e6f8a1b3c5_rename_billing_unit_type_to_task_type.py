"""rename_billing_unit_type_to_task_type

Renames mm_services.billing_unit_type to task_type. The pay-per-use Kafka
consumer now sources the LLM/non-LLM billing decision from this column
(via mm_services) instead of the span attribute stamped at request time.

Revision ID: d4e6f8a1b3c5
Revises: 5c6faec0df77
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd4e6f8a1b3c5'
down_revision: Union[str, Sequence[str], None] = '5c6faec0df77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('mm_services', 'billing_unit_type', new_column_name='task_type')


def downgrade() -> None:
    op.alter_column('mm_services', 'task_type', new_column_name='billing_unit_type')
