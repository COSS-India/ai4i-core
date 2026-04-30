"""
PII Default Domains Seeder

Seeds default PII types and policies into policy_db.
Ported from the deleted Alembic migrations:
  - f1e2d3c4b5a6_seed_default_pii_domain_policies.py  (general, healthcare, financial, education)
  - a7b8c9d0e1f2_seed_logistics_domain_policies.py     (logistics, logistics_hindi)

Schema (policy_db):
  pii_types           — entity types with regex and mask format
  pii_policy          — named policies with supported languages
  policy_pii_types    — many-to-many join
"""

import uuid
from infrastructure.databases.core.base_seeder import BaseSeeder


def _uid(*parts: str) -> str:
    """Deterministic UUID from label so re-runs are idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ":".join(parts)))


# ---------------------------------------------------------------------------
# PII type definitions  (label → regex, mask_format)
# mask_format: "redact" | "partial" | "full"
# ---------------------------------------------------------------------------
_PII_TYPES = [
    ("EMAIL",        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",      "redact"),
    ("PHONE",        r"\b(?:\+91[\s\-]?)?[6-9]\d{9}\b",                              "redact"),
    ("AADHAAR_UID",  r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",                          "redact"),
    ("PAN_CARD",     r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",                                   "redact"),
    ("PERSON",       r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b",                           "redact"),
    ("PIN_CODE",     r"\b[1-9][0-9]{5}\b",                                            "partial"),
    ("CREDIT_CARD",  r"\b(?:\d{4}[\s\-]?){3}\d{4}\b",                               "partial"),
    ("PATIENT_CODE", r"\bHC-\d{4,8}\b",                                              "redact"),
    ("MRN",          r"\bMRN\s*[:#\-]?\s*\d{6,12}\b",                               "redact"),
    ("TRACKING_ID",  r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b", "redact"),
    ("COURIER_REF",  r"\b1Z[0-9A-Z]{16}\b",                                          "redact"),
    ("VEHICLE_REG",  r"\b[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{1,3}\s?[0-9]{4}\b",         "redact"),
    ("ADDRESS",      r"\b(?:(?:Flat|House|Plot|Door|H\.?No\.?|F\.?No\.?)\s*[#\-]?\s*\w+[\w\s,\-\/]{5,80}(?:Nagar|Colony|Road|Street|Lane|Marg|Chowk|Bazaar|Gali|Layout|Sector|Phase|Block|Area|District|Dist\.?|Taluka|Tehsil|Village|Vill\.?)[\w\s,\-\.]{0,60})\b", "redact"),
]

# ---------------------------------------------------------------------------
# Policy definitions  (name → description, is_global, supported_languages, [pii_type_labels])
# ---------------------------------------------------------------------------
_POLICIES = [
    (
        "General",
        "Baseline PII for mixed content",
        True,
        ["en", "hi"],
        ["EMAIL", "PHONE", "PAN_CARD", "AADHAAR_UID", "PIN_CODE"],
    ),
    (
        "Healthcare",
        "PHI, clinical codes, and common ID patterns",
        False,
        ["en"],
        ["PATIENT_CODE", "MRN", "EMAIL", "PHONE", "AADHAAR_UID", "PAN_CARD", "PERSON", "PIN_CODE"],
    ),
    (
        "Financial",
        "Payments and tax-related identifiers",
        False,
        ["en"],
        ["CREDIT_CARD", "PAN_CARD", "AADHAAR_UID", "EMAIL", "PHONE"],
    ),
    (
        "Education",
        "Student and institution context",
        False,
        ["en"],
        ["EMAIL", "PHONE", "PERSON", "PIN_CODE"],
    ),
    (
        "Logistics",
        "Shipments, tracking references, vehicle plates, consignee PII",
        False,
        ["en"],
        ["TRACKING_ID", "COURIER_REF", "VEHICLE_REG", "ADDRESS", "EMAIL", "PHONE", "AADHAAR_UID", "PAN_CARD", "PERSON", "PIN_CODE"],
    ),
    (
        "Logistics Hindi",
        "Logistics domain for Hindi content — use X-Language: hi with /redact",
        False,
        ["hi"],
        ["TRACKING_ID", "COURIER_REF", "VEHICLE_REG", "ADDRESS", "EMAIL", "PHONE", "AADHAAR_UID", "PAN_CARD", "PERSON", "PIN_CODE"],
    ),
]


class PiiDefaultDomainsSeeder(BaseSeeder):
    """Seed default PII types and domain policies into policy_db."""

    database = "policy_db"

    def run(self, adapter):
        existing = adapter.fetch_one("SELECT COUNT(*) FROM pii_policy")
        if existing and existing[0] > 0:
            print("    ⚠ PII policies already exist, skipping")
            return

        # 1. Insert PII types
        type_id_map = {}
        for label, regex, mask_format in _PII_TYPES:
            type_id = _uid("pii_type", label)
            type_id_map[label] = type_id
            adapter.execute(
                """
                INSERT INTO pii_types (pii_type_id, pii_type_label, regex_pattern, is_active, mask_format)
                VALUES (:id, :label, :regex, true, :mask)
                ON CONFLICT (pii_type_label) DO NOTHING
                """,
                {"id": type_id, "label": label, "regex": regex, "mask": mask_format},
            )
        print(f"    ✓ Seeded {len(_PII_TYPES)} PII types")

        # 2. Insert policies + join rows
        for name, description, is_global, languages, type_labels in _POLICIES:
            policy_id = _uid("pii_policy", name)
            import json
            adapter.execute(
                """
                INSERT INTO pii_policy (policy_id, name, description, is_active, is_global, supported_languages)
                VALUES (:id, :name, :desc, true, :global, CAST(:langs AS jsonb))
                ON CONFLICT (name) DO NOTHING
                """,
                {
                    "id": policy_id,
                    "name": name,
                    "desc": description,
                    "global": is_global,
                    "langs": json.dumps(languages),
                },
            )
            for label in type_labels:
                join_id = _uid("policy_pii_type", name, label)
                adapter.execute(
                    """
                    INSERT INTO policy_pii_types (id, policy_id, pii_type_id)
                    VALUES (:id, :policy_id, :type_id)
                    ON CONFLICT ON CONSTRAINT uq_policy_pii_type DO NOTHING
                    """,
                    {"id": join_id, "policy_id": policy_id, "type_id": type_id_map[label]},
                )

        policy_names = ", ".join(name for name, *_ in _POLICIES)
        print(f"    ✓ Seeded {len(_POLICIES)} PII domain policies: {policy_names}")
