"""seed logistics PII domain policies (inactive until activated)

Revision ID: a7b8c9d0e1f2
Revises: f1e2d3c4b5a6
Create Date: 2026-03-26
"""

import json
from typing import Dict, List, Tuple

from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f1e2d3c4b5a6"
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


def _logistics_rules() -> List[Dict]:
    """Shared rules for logistics; use X-Language header hi/ta/mr with regional domains."""
    return [
        {
            "entity_type": "TRACKING_ID",
            "action": "REDACT_TAG",
            "config": {"tag_label": "[TRACKING]"},
            "custom_regex": r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b",
        },
        {
            "entity_type": "COURIER_REF",
            "action": "REDACT_TAG",
            "config": {"tag_label": "[REF]"},
            "custom_regex": r"\b1Z[0-9A-Z]{16}\b",
        },
        {
            "entity_type": "VEHICLE_REG",
            "action": "REDACT_TAG",
            "config": {"tag_label": "[VEHICLE]"},
            "custom_regex": r"\b[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{1,3}\s?[0-9]{4}\b",
        },
        {"entity_type": "EMAIL", "action": "REDACT", "config": {}},
        {"entity_type": "PHONE", "action": "REDACT", "config": {}},
        {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
        {"entity_type": "PAN_CARD", "action": "REDACT", "config": {}},
        {"entity_type": "PERSON", "action": "REDACT", "config": {}},
        {"entity_type": "PIN_CODE", "action": "MASK", "config": {"mask_char": "X"}},
    ]


_LOGISTICS_DOMAINS: List[Tuple[str, bool, str]] = [
    (
        "logistics",
        False,
        _policy(
            "Logistics — shipments, tracking references, vehicle plates, consignee PII (English)",
            _logistics_rules(),
        ),
    ),
    (
        "logistics_hindi",
        False,
        _policy(
            "Logistics — Hindi content; use header X-Language: hi with /redact",
            _logistics_rules(),
        ),
    ),
    (
        "logistics_tamil",
        False,
        _policy(
            "Logistics — Tamil content; use header X-Language: ta with /redact",
            _logistics_rules(),
        ),
    ),
    (
        "logistics_marathi",
        False,
        _policy(
            "Logistics — Marathi content; use header X-Language: mr with /redact",
            _logistics_rules(),
        ),
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for domain_id, is_active, policy_json_str in _LOGISTICS_DOMAINS:
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
            "('logistics', 'logistics_hindi', 'logistics_tamil', 'logistics_marathi')"
        )
    )
