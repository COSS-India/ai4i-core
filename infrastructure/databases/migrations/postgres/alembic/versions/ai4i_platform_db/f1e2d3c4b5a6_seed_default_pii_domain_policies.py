"""seed default PII domain policies (inactive until activated)

Revision ID: f1e2d3c4b5a6
Revises: e8b3d0c1f2a4
Create Date: 2026-03-26
"""

import json
from typing import Dict, List, Tuple

from alembic import op
import sqlalchemy as sa

revision = "f1e2d3c4b5a6"
down_revision = "e8b3d0c1f2a4"
branch_labels = None
depends_on = None


def _policy(meta_description: str, rules: List[Dict]) -> str:
    return json.dumps(
        {
            "meta": {"version": "1.0", "description": meta_description},
            "rules": rules,
        },
        separators=(",", ":"),
    )


# Rules: entity_type + action + optional config. Use custom_regex for patterns not in pattern_library.
# DetectionEngine reads custom_regex (not "regex"). KB-backed entities omit custom_regex.
_DEFAULT_DOMAINS: List[Tuple[str, bool, str]] = [
    (
        "healthcare",
        False,
        _policy(
            "Healthcare — PHI, clinical codes, and common ID patterns",
            [
                {
                    "entity_type": "PATIENT_CODE",
                    "action": "REDACT_TAG",
                    "config": {"tag_label": "[PATIENT_CODE]"},
                    "custom_regex": r"\bHC-\d{4,8}\b",
                },
                {"entity_type": "MRN", "action": "REDACT_TAG", "config": {"tag_label": "[MRN]"}, "custom_regex": r"\bMRN\s*[:#-]?\s*\d{6,12}\b"},
                {"entity_type": "EMAIL", "action": "REDACT", "config": {}},
                {"entity_type": "PHONE", "action": "REDACT", "config": {}},
                {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
                {"entity_type": "PAN_CARD", "action": "REDACT", "config": {}},
                {"entity_type": "PERSON", "action": "REDACT", "config": {}},
                {"entity_type": "PIN_CODE", "action": "MASK", "config": {"mask_char": "X"}},
            ],
        ),
    ),
    (
        "financial",
        False,
        _policy(
            "Financial — payments and tax-related identifiers",
            [
                {"entity_type": "CREDIT_CARD", "action": "REDACT", "config": {}},
                {"entity_type": "PAN_CARD", "action": "REDACT", "config": {}},
                {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
                {"entity_type": "EMAIL", "action": "REDACT", "config": {}},
                {"entity_type": "PHONE", "action": "REDACT", "config": {}},
            ],
        ),
    ),
    (
        "general",
        False,
        _policy(
            "General — baseline PII for mixed content",
            [
                {"entity_type": "EMAIL", "action": "REDACT", "config": {}},
                {"entity_type": "PHONE", "action": "REDACT", "config": {}},
                {"entity_type": "PAN_CARD", "action": "REDACT", "config": {}},
                {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
                {"entity_type": "PIN_CODE", "action": "MASK", "config": {"mask_char": "X"}},
            ],
        ),
    ),
    (
        "education",
        False,
        _policy(
            "Education — student / institution context (baseline rules)",
            [
                {"entity_type": "EMAIL", "action": "REDACT", "config": {}},
                {"entity_type": "PHONE", "action": "REDACT", "config": {}},
                {"entity_type": "PERSON", "action": "REDACT", "config": {}},
                {"entity_type": "PIN_CODE", "action": "MASK", "config": {"mask_char": "X"}},
            ],
        ),
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for domain_id, is_active, policy_json_str in _DEFAULT_DOMAINS:
        row = conn.execute(
            sa.text("SELECT 1 FROM domain_policies WHERE domain_id = :d LIMIT 1"),
            {"d": domain_id},
        ).first()
        if row:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO domain_policies (domain_id, is_active, policy_json)
                VALUES (:domain_id, :is_active, CAST(:policy_json AS jsonb))
                """
            ),
            {
                "domain_id": domain_id,
                "is_active": is_active,
                "policy_json": policy_json_str,
            },
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM domain_policies WHERE domain_id IN "
            "('healthcare', 'financial', 'general', 'education')"
        )
    )
