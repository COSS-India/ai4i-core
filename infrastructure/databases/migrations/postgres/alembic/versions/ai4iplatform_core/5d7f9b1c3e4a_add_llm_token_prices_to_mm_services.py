"""add cached input and output token prices to mm_services

LLM services get two more prices next to the existing one: cost_per_unit
stays as is (for LLM it is the input token price; for other task types their
single price), and these two are per the same unit_size:

* cached_input_cost_per_unit: price of cached input tokens
* output_cost_per_unit: price of output tokens

Both are nullable and only used for LLM services. Existing LLM services get
their current cost_per_unit copied into both, so their billing is unchanged
until an admin sets different prices.

Revision ID: 5d7f9b1c3e4a
Revises: 4c6e8a0b2d3f
Create Date: 2026-10-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5d7f9b1c3e4a"
down_revision: Union[str, None] = "4c6e8a0b2d3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "mm_services"
NEW_PRICES = ("cached_input_cost_per_unit", "output_cost_per_unit")
MAX_PRICE = 10_000_000


def _check_name(column: str) -> str:
    return f"ck_mm_services_{column}_range"


def upgrade() -> None:
    for column in NEW_PRICES:
        op.add_column(TABLE, sa.Column(column, sa.Numeric(16, 8), nullable=True))
        op.create_check_constraint(
            _check_name(column), TABLE, f"{column} IS NULL OR ({column} >= 0 AND {column} <= {MAX_PRICE})"
        )

    # Existing LLM services: apply their single price to both new prices,
    # with the same unit_size. Matches billing's case-insensitive task_type.
    op.execute(
        f"""
        UPDATE {TABLE}
           SET cached_input_cost_per_unit = cost_per_unit,
               output_cost_per_unit       = cost_per_unit
         WHERE lower(task_type) = 'llm'
           AND cost_per_unit IS NOT NULL
        """
    )


def downgrade() -> None:
    for column in reversed(NEW_PRICES):
        op.drop_constraint(_check_name(column), TABLE, type_="check")
        op.drop_column(TABLE, column)
