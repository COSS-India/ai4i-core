"""seed default PII definitions per domain

The seeded 'PII' row holds every default entity in one flat list, so a policy
for one domain picks up the others' entities too (UPI_ID and TRANSACTION_ID
mask ordinary Education text). This adds one PII definition per domain
(Education PII, Finance PII, Healthcare PII) that a policy can attach on its
own. The combined 'PII' row stays, because policy.policy_type_id may point at
it and the database does not enforce that reference.

A name an admin already uses (any case) is left alone, so re-running or
upgrading a database with a hand-made 'Education PII' changes nothing.

Revision ID: b7d9f1a3c5e8
Revises: e2f4a6c8b0d3
Create Date: 2026-10-23

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d9f1a3c5e8"
down_revision: Union[str, None] = "e2f4a6c8b0d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0001-0000-0000-0000-000000000004"

_DOMAIN_PII_DEFINITIONS = {
    "Education PII": [
        {
            "entity_name": "STUDENT_NAME",
            "examples": ["Arjun Kumar", "Priya Sharma", "Ravi Verma"],
            "regex": r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3}\b",
        },
        {
            "entity_name": "STUDENT_ID",
            "examples": ["EDU20231234", "STU2024567", "SCH12345"],
            "regex": r"\b[A-Z]{2,5}\d{4,10}\b",
        },
        {
            "entity_name": "EMAIL_ADDRESS",
            "examples": [
                "arjun@college.edu",
                "student@university.ac.in",
                "user@school.org",
            ],
            "regex": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        },
        {
            "entity_name": "PHONE_NUMBER",
            "examples": ["+91 9876543210", "9876543210", "9123456789"],
            "regex": r"\b(?:\+?\d{1,3}[\s-]?)?\d{10}\b",
        },
        {
            "entity_name": "DATE_OF_BIRTH",
            "examples": ["12-08-2004", "01-01-1990", "25-12-2000"],
            "regex": r"\b(0[1-9]|[12]\d|3[01])[-/](0[1-9]|1[0-2])[-/](19|20)\d{2}\b",
        },
        {
            "entity_name": "ADDRESS",
            "examples": [
                "24 MG Road, Chennai",
                "12 Park Street, Delhi",
                "5 Lake View, Mumbai",
            ],
            "regex": r"\d+[\w\s,.-]+",
        },
    ],
    "Finance PII": [
        {
            "entity_name": "BANK_ACCOUNT_NUMBER",
            "examples": ["123456789012", "987654321098", "112233445566"],
            "regex": r"\b\d{9,18}\b",
        },
        {
            "entity_name": "CREDIT_DEBIT_CARD",
            "examples": [
                "4111 1111 1111 1111",
                "5500 0000 0000 0004",
                "3714 496353 98431",
            ],
            "regex": r"\b(?:\d[ -]*?){13,16}\b",
        },
        {
            "entity_name": "IFSC_CODE",
            "examples": ["SBIN0000456", "HDFC0001234", "ICIC0005678"],
            "regex": r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
        },
        {
            "entity_name": "PAN_NUMBER",
            "examples": ["ABCDE1234F", "PQRST5678G", "XYZWV9012H"],
            "regex": r"\b[A-Z]{5}\d{4}[A-Z]\b",
        },
        {
            "entity_name": "TRANSACTION_ID",
            "examples": ["TXN987654321", "TRX20231009", "PAY123456789"],
            "regex": r"\b[A-Z0-9]{8,20}\b",
        },
        {
            "entity_name": "UPI_ID",
            "examples": ["arjun@upi", "user@okaxis", "merchant@ybl"],
            "regex": r"\b[\w.-]+@[\w.-]+\b",
        },
    ],
    "Healthcare PII": [
        {
            "entity_name": "PATIENT_NAME",
            "examples": ["Meena Raj", "Suresh Kumar", "Anita Singh"],
            "regex": r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,3}\b",
        },
        {
            "entity_name": "MEDICAL_RECORD_NUMBER",
            "examples": ["UHID123456", "MRN456789", "HOS987654"],
            "regex": r"\b[A-Z]{2,5}\d{4,10}\b",
        },
        {
            "entity_name": "AADHAAR_NUMBER",
            "examples": ["1234 5678 9012", "9876 5432 1098", "1111 2222 3333"],
            "regex": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        },
        {
            "entity_name": "PHONE_NUMBER",
            "examples": ["9876543210", "+91 9876543210", "8123456789"],
            "regex": r"\b(?:\+?\d{1,3}[\s-]?)?\d{10}\b",
        },
        {
            "entity_name": "HEALTH_INSURANCE_ID",
            "examples": ["HIN9876543", "INS123456789", "POL987654321"],
            "regex": r"\b[A-Z0-9]{6,20}\b",
        },
        {
            "entity_name": "DIAGNOSIS_CODE_ICD10",
            "examples": ["E11.9", "J18.1", "I10"],
            "regex": r"\b[A-TV-Z][0-9]{2}(\.[0-9A-TV-Z]{1,4})?\b",
        },
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, custom_field in _DOMAIN_PII_DEFINITIONS.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO policy_type (policy_type, policy_fields, created_by, updated_by)
                SELECT :policy_type, CAST(:policy_fields AS JSONB), :seeder_id, :seeder_id
                 WHERE NOT EXISTS (
                       SELECT 1 FROM policy_type WHERE lower(policy_type) = lower(:policy_type)
                 )
                """
            ),
            {
                "policy_type": name,
                "policy_fields": json.dumps({"custom_field": custom_field}),
                "seeder_id": SEEDER_ID,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM policy_type WHERE created_by = :seeder_id"),
        {"seeder_id": SEEDER_ID},
    )
