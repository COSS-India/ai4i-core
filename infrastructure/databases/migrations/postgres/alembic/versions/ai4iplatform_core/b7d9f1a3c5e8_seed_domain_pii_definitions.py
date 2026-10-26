"""seed default PII definitions per domain

The seeded 'PII' row holds every default entity in one flat list, so a policy
for one domain picks up the others' entities too (UPI_ID and TRANSACTION_ID
mask ordinary Education text). This adds one PII definition per domain
(Education PII, Finance PII, Healthcare PII) that a policy can attach on its
own. The combined 'PII' row stays, because policy.policy_type_id may point at
it and the database does not enforce that reference.

Each kind of PII is defined once. Where a Presidio built-in detects it better
than the story's regex, the definition names the built-in under
model_supported_field instead of seeding a custom copy; the PII Types list
already shows every built-in, so a custom copy would list it twice.

  Student Name, Patient Name -> PERSON. The story's regex matches any run of
      capitalised words ("Machine Learning Course") and misses lowercase and
      single names; spaCy NER does not.
  Email -> EMAIL_ADDRESS. Same detections as the story's regex; the built-in
      also checks the domain.
  Phone Number -> PHONE_NUMBER. libphonenumber finds +91-98765-43210,
      098765 43210 and landlines, which the story's regex misses.
  Credit / Debit Card -> CREDIT_CARD. Luhn check; the story's regex masks any
      13-16 digits.
  Aadhaar Number -> IN_AADHAAR. Verhoeff check; the story's regex masks any
      12 digits.
  PAN Number -> IN_PAN. Also matches lowercase and checks the holder-type
      letter.

The rest have no built-in and stay custom, with the story's regexes, except
Address. Presidio has no address entity (LOCATION only catches the city), and
the story's regex masks everything after the first digit ("5 students in
class"), so Address uses a stricter regex: a house number, then street words
ending in a keyword such as Road, Street or Nagar (or "Sector 21"), then an
optional locality, city and PIN code. It misses addresses written all in
lowercase. Date of Birth stays custom rather than DATE_TIME, which masks every
date and weekday.

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


def _model_entities(*names: str):
    return [{"en": [{"entity_name": name} for name in names]}]


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


_DOMAIN_PII_DEFINITIONS = {
    "Education PII": {
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
                "examples": [
                    "24 MG Road, Chennai",
                    "12 Park Street, Delhi",
                    "5 Lake View, Mumbai",
                ],
                "regex": _ADDRESS_REGEX,
            },
        ],
        "model_supported_field": _model_entities("PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"),
    },
    "Finance PII": {
        "custom_field": [
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
                "regex": r"\b[A-Z0-9]{8,20}\b",
            },
            {
                "entity_name": "UPI_ID",
                "examples": ["arjun@upi", "user@okaxis", "merchant@ybl"],
                "regex": r"\b[\w.-]+@[\w.-]+\b",
            },
        ],
        "model_supported_field": _model_entities("CREDIT_CARD", "IN_PAN"),
    },
    "Healthcare PII": {
        "custom_field": [
            {
                "entity_name": "MEDICAL_RECORD_NUMBER",
                "examples": ["UHID123456", "MRN456789", "HOS987654"],
                "regex": r"\b[A-Z]{2,5}\d{4,10}\b",
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
        "model_supported_field": _model_entities("PERSON", "IN_AADHAAR", "PHONE_NUMBER"),
    },
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, policy_fields in _DOMAIN_PII_DEFINITIONS.items():
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
                "policy_fields": json.dumps(policy_fields),
                "seeder_id": SEEDER_ID,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM policy_type WHERE created_by = :seeder_id"),
        {"seeder_id": SEEDER_ID},
    )
