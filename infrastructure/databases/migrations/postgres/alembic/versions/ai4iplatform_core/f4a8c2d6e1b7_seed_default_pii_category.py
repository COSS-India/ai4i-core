"""seed default pii category

Seeds the built-in "Security & Privacy" category and its "PII Guardrails"
sub-category so every adopter has baseline PII protection without creating
either manually. Both are seeded active.

Kept separate from the DDL revision (e3df9d24b593) so the data can be rolled
back and re-applied without touching the tables. ``ON CONFLICT DO NOTHING``
makes re-running ``migrate.sh all upgrade`` a no-op.

Revision ID: f4a8c2d6e1b7
Revises: e3df9d24b593
Create Date: 2026-10-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4a8c2d6e1b7"
down_revision: Union[str, None] = "e3df9d24b593"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORY_NAME = "Security & Privacy"
_CATEGORY_DESCRIPTION = (
    "Guardrails that detect and protect personally identifiable information "
    "across requests, responses, and storage."
)
_SUB_CATEGORY_NAME = "PII Guardrails"
_SUB_CATEGORY_DESCRIPTION = (
    "Configure PII types, policies, and enforcement for personally "
    "identifiable information."
)
    

def upgrade() -> None:
    op.execute(
        "INSERT INTO category (name, description, is_active) VALUES\n"
        f"    ('{_CATEGORY_NAME}', '{_CATEGORY_DESCRIPTION}', true)\n"
        "ON CONFLICT (name) DO NOTHING;"
    )
    op.execute(
        "INSERT INTO sub_category (name, description, category_id, is_active)\n"
        f"SELECT '{_SUB_CATEGORY_NAME}', '{_SUB_CATEGORY_DESCRIPTION}', id, true\n"
        f"FROM category WHERE name = '{_CATEGORY_NAME}'\n"
        "ON CONFLICT (name) DO NOTHING;"
    )


def downgrade() -> None:
    # Targeted deletes, never TRUNCATE — admin-created rows are not this
    # revision's to remove. The RESTRICT FKs make this fail if policies or
    # other sub-categories still reference the seeded rows; remove those first.
    op.execute(f"DELETE FROM sub_category WHERE name = '{_SUB_CATEGORY_NAME}';")
    op.execute(f"DELETE FROM category WHERE name = '{_CATEGORY_NAME}';")
