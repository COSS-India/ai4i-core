"""
PII Default Domains Seeder

Seeds default PII patterns and domain policies into ai4i_platform.
Ported from the deleted Alembic migrations:
  - f1e2d3c4b5a6_seed_default_pii_domain_policies.py  (general, healthcare, financial, education)
  - a7b8c9d0e1f2_seed_logistics_domain_policies.py     (logistics, logistics_hindi)

Schema (ai4i_platform):
  pattern_library  — regex patterns per entity label and language
  domain_policies  — named domains with JSON rules blob
"""

import json
from infrastructure.databases.core.base_seeder import BaseSeeder


_PATTERNS = [
    ("EMAIL",        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ("PHONE",        r"\b(?:\+91[\s\-]?)?[6-9]\d{9}\b"),
    ("AADHAAR_UID",  r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
    ("PAN_CARD",     r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    ("PERSON",       r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b"),
    ("PIN_CODE",     r"\b[1-9][0-9]{5}\b"),
    ("CREDIT_CARD",  r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
    ("PATIENT_CODE", r"\bHC-\d{4,8}\b"),
    ("MRN",          r"\bMRN\s*[:#\-]?\s*\d{6,12}\b"),
    ("TRACKING_ID",  r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b"),
    ("COURIER_REF",  r"\b1Z[0-9A-Z]{16}\b"),
    ("VEHICLE_REG",  r"\b[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{1,3}\s?[0-9]{4}\b"),
    ("ADDRESS",      r"\b(?:(?:Flat|House|Plot|Door|H\.?No\.?|F\.?No\.?)\s*[#\-]?\s*\w+[\w\s,\-\/]{5,80}(?:Nagar|Colony|Road|Street|Lane|Marg|Chowk|Bazaar|Gali|Layout|Sector|Phase|Block|Area|District|Dist\.?|Taluka|Tehsil|Village|Vill\.?)[\w\s,\-\.]{0,60})\b"),
]


def _redact(et):
    return {"entity_type": et, "action": "REDACT_TAG", "config": {"tag_label": f"[{et}]"}}

def _mask(et):
    return {"entity_type": et, "action": "MASK", "config": {"mask_char": "X"}}


_DOMAINS = [
    (
        "general",
        "Baseline PII for mixed content",
        True,
        [_redact("EMAIL"), _redact("PHONE"), _redact("PAN_CARD"), _redact("AADHAAR_UID"), _mask("PIN_CODE")],
    ),
    (
        "healthcare",
        "PHI, clinical codes, and common ID patterns",
        False,
        [_redact("PATIENT_CODE"), _redact("MRN"), _redact("EMAIL"), _redact("PHONE"),
         _redact("AADHAAR_UID"), _redact("PAN_CARD"), _redact("PERSON"), _mask("PIN_CODE")],
    ),
    (
        "financial",
        "Payments and tax-related identifiers",
        False,
        [_mask("CREDIT_CARD"), _redact("PAN_CARD"), _redact("AADHAAR_UID"), _redact("EMAIL"), _redact("PHONE")],
    ),
    (
        "education",
        "Student and institution context",
        False,
        [_redact("EMAIL"), _redact("PHONE"), _redact("PERSON"), _mask("PIN_CODE")],
    ),
    (
        "logistics",
        "Shipments, tracking references, vehicle plates, consignee PII",
        False,
        [_redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"), _redact("ADDRESS"),
         _redact("EMAIL"), _redact("PHONE"), _redact("AADHAAR_UID"), _redact("PAN_CARD"),
         _redact("PERSON"), _mask("PIN_CODE")],
    ),
    (
        "logistics_hindi",
        "Logistics domain for Hindi content — use X-Language: hi with /redact",
        False,
        [_redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"), _redact("ADDRESS"),
         _redact("EMAIL"), _redact("PHONE"), _redact("AADHAAR_UID"), _redact("PAN_CARD"),
         _redact("PERSON"), _mask("PIN_CODE")],
    ),
]


class PiiDefaultDomainsSeeder(BaseSeeder):
    """Seed default PII patterns and domain policies into ai4i_platform."""

    database = "ai4i_platform"

    def run(self, adapter):
        existing = adapter.fetch_one("SELECT COUNT(*) FROM domain_policies")
        if existing and existing[0] > 0:
            print("    ⚠ PII domain policies already exist, skipping")
            return

        for entity_label, regex in _PATTERNS:
            adapter.execute(
                """
                INSERT INTO pattern_library (entity_label, lang_code, regex_pattern, risk_score, is_active)
                VALUES (:label, 'all', :regex, 1.0, true)
                ON CONFLICT ON CONSTRAINT uq_pattern_entity_lang DO NOTHING
                """,
                {"label": entity_label, "regex": regex},
            )
        print(f"    ✓ Seeded {len(_PATTERNS)} PII patterns into pattern_library")

        for domain_id, description, is_active, rules in _DOMAINS:
            policy_json = json.dumps({
                "meta": {"version": "1.0", "description": description},
                "rules": rules,
            })
            adapter.execute(
                """
                INSERT INTO domain_policies (domain_id, is_active, policy_json)
                VALUES (:id, :active, CAST(:json AS jsonb))
                ON CONFLICT (domain_id) DO NOTHING
                """,
                {"id": domain_id, "active": is_active, "json": policy_json},
            )

        domain_names = ", ".join(d for d, *_ in _DOMAINS)
        print(f"    ✓ Seeded {len(_DOMAINS)} PII domain policies: {domain_names}")
