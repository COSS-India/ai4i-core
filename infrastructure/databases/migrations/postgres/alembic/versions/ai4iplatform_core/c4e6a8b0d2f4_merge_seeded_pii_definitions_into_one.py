"""merge the seeded PII definitions into one 'PII' policy type

b7d9f1a3c5e8 seeded Education PII, Finance PII and Healthcare PII next to the
older seeded 'PII' row, so the PII Types list showed four default definitions
and the same entities more than once. The defaults are one 'PII' policy type
holding the custom fields only. Built-ins (PERSON, EMAIL_ADDRESS, IN_PAN, ...)
are not seeded into it: the PII Types list already offers every one of them.

Every earlier seeded row (created_by one of the earlier seeder ids) is
removed, and a policy that listed one of them in policy_type_id lists the new
row instead; the database does not enforce that reference, so a dropped id
would leave the policy with nothing to mask, and no error. A 'PII' row an
admin made is left alone, which is why rows are matched by seeder id and not by
name.

Cached policies (Redis, 1 hour TTL) keep the old definitions until they are
re-cached or expire.

Revision ID: c4e6a8b0d2f4
Revises: b8d2f4a6c0e1
Create Date: 2026-10-27

"""
import importlib.util
import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e6a8b0d2f4"
down_revision: Union[str, None] = "b8d2f4a6c0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0001-0000-0000-0000-000000000005"
# b3f1a9e2c7d5, c2e4a6f8b0d1, f4a7c2e9d1b3 (the old 'PII' row) and b7d9f1a3c5e8.
EARLIER_SEEDER_IDS = [
    "5eed0001-0000-0000-0000-000000000001",
    "5eed0001-0000-0000-0000-000000000002",
    "5eed0001-0000-0000-0000-000000000003",
    "5eed0001-0000-0000-0000-000000000004",
]

# Custom regexes are matched case-sensitively, so the keywords are (?i:...).
_ADDRESS_REGEX = (
    r"\b(?:(?:Flat|House|Door|Plot|Shop|H)\.?\s?(?:No\.?\s?)?)?"
    r"\d{1,5}[A-Za-z]?(?:[/-]\d{1,4}[A-Za-z]?)?,?\s+"
    r"(?:(?:(?:\d{1,3}(?:st|nd|rd|th)|[A-Z][A-Za-z.]*),?\s+){1,4}"
    r"(?i:Road|Rd|Street|St|Lane|Nagar|Colony|Marg|Avenue|Layout|Enclave|Vihar|Puram|View|Gardens?|Residency|Apartments?|Towers?|Society)\b\.?"
    r"|(?i:Sector|Block|Phase)\s+\d{1,4}[A-Za-z]?)"
    r"(?:,?\s+(?i:Sector|Block|Phase)\s+\d{1,4}[A-Za-z]?)?"
    r"(?:,\s*[A-Z][a-z]+(?:\s[A-Z][a-z]+)?){0,2}"
    r"(?:[\s,-]+\d{3}\s?\d{3}\b)?"
)

# The custom fields b7d9f1a3c5e8 seeded, unchanged; see its docstring for why
# each regex differs from the story where it does.
_PII_POLICY_FIELDS = {
    "custom_field": [
        {
            "entity_name": "STUDENT_ID",
            "examples": ["EDU20231234", "STU2024567", "SCH12345"],
            "regex": r"\b[A-Z]{2,5}\d{4,10}\b",
        },
        {
            "entity_name": "DATE_OF_BIRTH",
            "examples": ["12-08-2004", "01-01-1990", "25-12-2000"],
            "regex": r"\b(0[1-9]|[12]\d|3[01])[-/](0[1-9]|1[0-2])[-/](19|20)\d{2}\b",
        },
        {
            "entity_name": "ADDRESS",
            "examples": ["24 MG Road, Chennai", "12 Park Street, Delhi", "5 Lake View, Mumbai"],
            "regex": _ADDRESS_REGEX,
        },
        {
            "entity_name": "BANK_ACCOUNT_NUMBER",
            "examples": ["123456789012", "987654321098", "112233445566"],
            "regex": r"\b\d{9,18}\b",
        },
        {
            "entity_name": "IFSC_CODE",
            "examples": ["SBIN0000456", "HDFC0001234", "ICIC0005678"],
            "regex": r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        },
        {
            "entity_name": "TRANSACTION_ID",
            "examples": ["TXN987654321", "TRX20231009", "PAY123456789"],
            "regex": r"\b[A-Z]{2,5}\d{8,15}\b",
        },
        {
            "entity_name": "UPI_ID",
            "examples": ["arjun@upi", "user@okaxis", "merchant@ybl"],
            "regex": r"\b[\w.-]+@[A-Za-z]{2,64}\b(?!\w|\.\w)",
        },
        {
            "entity_name": "MEDICAL_RECORD_NUMBER",
            "examples": ["UHID123456", "MRN456789", "HOS987654"],
            "regex": r"\b[A-Z]{2,5}\d{4,10}\b",
        },
        {
            "entity_name": "HEALTH_INSURANCE_ID",
            "examples": ["HIN9876543", "INS123456789", "POL987654321"],
            "regex": r"\b[A-Z]{2,5}\d{6,15}\b",
        },
        {
            "entity_name": "DIAGNOSIS_CODE_ICD10",
            "examples": ["E11.9", "J18.1", "I10"],
            "regex": r"\b[A-TV-Z][0-9]{2}(\.[0-9A-TV-Z]{1,4})?\b",
        },
    ]
}


def upgrade() -> None:
    bind = op.get_bind()
    # A downgrade keeps this row while a policy lists it; reuse it then.
    new_id = bind.execute(
        sa.text("SELECT id FROM policy_type WHERE created_by = :seeder_id"),
        {"seeder_id": SEEDER_ID},
    ).scalar()
    if new_id is None:
        new_id = bind.execute(
            sa.text(
                """
                INSERT INTO policy_type (policy_type, policy_fields, created_by, updated_by)
                VALUES ('PII', CAST(:policy_fields AS JSONB), :seeder_id, :seeder_id)
                RETURNING id
                """
            ),
            {"policy_fields": json.dumps(_PII_POLICY_FIELDS), "seeder_id": SEEDER_ID},
        ).scalar_one()

    old_ids = [
        row.id
        for row in bind.execute(
            sa.text("SELECT id FROM policy_type WHERE created_by = ANY(:seeder_ids)"),
            {"seeder_ids": EARLIER_SEEDER_IDS},
        )
    ]
    if not old_ids:
        return

    bind.execute(
        sa.text(
            """
            UPDATE policy
               SET policy_type_id = ARRAY(
                       SELECT DISTINCT CASE WHEN t = ANY(:old_ids) THEN :new_id ELSE t END
                         FROM unnest(policy_type_id) AS t
                   )
             WHERE policy_type_id && CAST(:old_ids AS INTEGER[])
            """
        ),
        {"old_ids": old_ids, "new_id": new_id},
    )
    bind.execute(
        sa.text("DELETE FROM policy_type WHERE id = ANY(:old_ids)"),
        {"old_ids": old_ids},
    )


def _domain_seed_migration():
    path = Path(__file__).with_name("b7d9f1a3c5e8_seed_domain_pii_definitions.py")
    spec = importlib.util.spec_from_file_location("seed_domain_pii_definitions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def downgrade() -> None:
    """Re-seed the three domain definitions, then drop the 'PII' row unless a
    policy lists it. The older 17-field 'PII' row is not restored, and
    policies moved onto the new row stay on it."""
    _domain_seed_migration().upgrade()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM policy_type
             WHERE created_by = :seeder_id
               AND NOT EXISTS (
                   SELECT 1 FROM policy p WHERE policy_type.id = ANY(p.policy_type_id)
               )
            """
        ),
        {"seeder_id": SEEDER_ID},
    )
