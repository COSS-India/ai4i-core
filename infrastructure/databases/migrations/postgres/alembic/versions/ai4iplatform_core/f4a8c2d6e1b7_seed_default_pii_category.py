"""seed default pii category

Revision ID: f4a8c2d6e1b7
Revises: e3df9d24b593
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
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
        sa.text(
            "INSERT INTO category (name, description, is_active)\n"
            "SELECT :name, :description, true\n"
            "WHERE NOT EXISTS (SELECT 1 FROM category WHERE name = :name)"
        ).bindparams(name=_CATEGORY_NAME, description=_CATEGORY_DESCRIPTION)
    )
    op.execute(
        sa.text(
            "INSERT INTO sub_category (name, description, category_id, is_active)\n"
            "SELECT :name, :description, c.id, true\n"
            "FROM category c\n"
            "WHERE c.name = :category_name\n"
            "  AND NOT EXISTS (SELECT 1 FROM sub_category WHERE name = :name)"
        ).bindparams(
            name=_SUB_CATEGORY_NAME,
            description=_SUB_CATEGORY_DESCRIPTION,
            category_name=_CATEGORY_NAME,
        )
    )


def downgrade() -> None:
    # Targeted deletes, never TRUNCATE — admin-created rows are not this
    # revision's to remove. The RESTRICT FKs make this fail if policies or
    # other sub-categories still reference the seeded rows; remove those first.
    op.execute(
        sa.text("DELETE FROM sub_category WHERE name = :name").bindparams(name=_SUB_CATEGORY_NAME)
    )
    op.execute(
        sa.text("DELETE FROM category WHERE name = :name").bindparams(name=_CATEGORY_NAME)
    )
