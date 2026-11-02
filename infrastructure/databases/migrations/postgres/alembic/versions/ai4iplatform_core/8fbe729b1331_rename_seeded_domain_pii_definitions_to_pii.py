"""rename the seeded domain PII definitions to 'PII'

b7d9f1a3c5e8 seeded Education PII, Finance PII and Healthcare PII. Their names
become 'PII'; their fields and ids stay, so policies keep pointing at them.

Only rows b7d9f1a3c5e8 seeded that still carry the seeded name are renamed, so
an admin's own row, or a seeded row an admin renamed, is left alone.

Downgrade restores each name, telling the rows apart by a custom field only
that definition seeded.

Revision ID: 8fbe729b1331
Revises: b8d2f4a6c0e1
Create Date: 2026-10-28

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8fbe729b1331"
down_revision: Union[str, None] = "b8d2f4a6c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0001-0000-0000-0000-000000000004"
NEW_NAME = "PII"
# Seeded name -> a custom field only that definition seeded.
SEEDED_NAMES = {
    "Education PII": "STUDENT_ID",
    "Finance PII": "BANK_ACCOUNT_NUMBER",
    "Healthcare PII": "MEDICAL_RECORD_NUMBER",
}


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE policy_type
               SET policy_type = :new_name
             WHERE created_by = :seeder_id
               AND policy_type = ANY(:names)
            """
        ),
        {"new_name": NEW_NAME, "seeder_id": SEEDER_ID, "names": list(SEEDED_NAMES)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    for name, entity_name in SEEDED_NAMES.items():
        bind.execute(
            sa.text(
                """
                UPDATE policy_type
                   SET policy_type = :name
                 WHERE created_by = :seeder_id
                   AND policy_type = :new_name
                   AND policy_fields @> CAST(:marker AS JSONB)
                """
            ),
            {
                "name": name,
                "seeder_id": SEEDER_ID,
                "new_name": NEW_NAME,
                "marker": json.dumps({"custom_field": [{"entity_name": entity_name}]}),
            },
        )
