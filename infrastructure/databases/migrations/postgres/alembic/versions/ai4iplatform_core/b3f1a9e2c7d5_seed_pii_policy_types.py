"""seed PII policy types

Revision ID: b3f1a9e2c7d5
Revises: c0d2e4f6a8b1
Create Date: 2026-10-09

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3f1a9e2c7d5"
down_revision: Union[str, None] = "c0d2e4f6a8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0001-0000-0000-0000-000000000001"

_POLICY_TYPES = [
    {
        "policy_type": "Education-PII",
        "policy_fields": {
            "custom_field": [
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
            ]
        },
    },
    {
        "policy_type": "Finance-PII",
        "policy_fields": {
            "custom_field": [
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
            ]
        },
    },
    {
        "policy_type": "Healthcare-PII",
        "policy_fields": {
            "custom_field": [
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
            ]
        },
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    for entry in _POLICY_TYPES:
        bind.execute(
            sa.text(
                """
                INSERT INTO policy_type (policy_type, policy_fields, created_by, updated_by)
                VALUES (:policy_type, :policy_fields, :seeder_id, :seeder_id)
                ON CONFLICT ON CONSTRAINT uq_policy_type_policy_type DO NOTHING
                """
            ),
            {
                "policy_type": entry["policy_type"],
                "policy_fields": json.dumps(entry["policy_fields"]),
                "seeder_id": SEEDER_ID,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM policy_type WHERE created_by = :seeder_id"
        ),
        {"seeder_id": SEEDER_ID},
    )
