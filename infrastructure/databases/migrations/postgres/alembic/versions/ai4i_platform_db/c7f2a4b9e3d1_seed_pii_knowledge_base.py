"""seed PII knowledge base: pattern_library, geo_library, domain_policies

Populates the three runtime tables that drive PII detection and redaction.
All inserts are idempotent (ON CONFLICT DO NOTHING / explicit existence checks)
so re-running the migration is safe.

Revision ID: c7f2a4b9e3d1
Revises: 96cd009dcbf3
Create Date: 2026-05-27
"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from alembic import op
import sqlalchemy as sa

revision: str = "c7f2a4b9e3d1"
down_revision: str = "96cd009dcbf3"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy(description: str, rules: List[Dict]) -> str:
    return json.dumps(
        {"meta": {"version": "1.0", "description": description}, "rules": rules},
        separators=(",", ":"),
    )


# ---------------------------------------------------------------------------
# 1. pattern_library
#    lang_code="all" expands to [en, hi, mr, ta] in KnowledgeBase.refresh().
#    Only entity types that appear in domain_policies WITHOUT a custom_regex
#    need entries here — domain-specific types (TRACKING_ID, PATIENT_CODE, etc.)
#    supply their own custom_regex inside policy_json and skip this table.
# ---------------------------------------------------------------------------

_PATTERNS: List[Tuple[str, str, str, float]] = [
    # (entity_label, lang_code, regex_pattern, risk_score)

    # Phone — Indian mobile (6-9XXXXXXXXX), optional +91/0/91 prefix.
    # Capturing group 1 isolates the 10-digit number so the redactor replaces
    # only the digits, not the prefix.
    (
        "PHONE", "all",
        r"(?:(?:\+?91|0)[\s\-]?)?([6-9]\d{9})\b",
        1.0,
    ),

    # Email — standard RFC-ish pattern.
    (
        "EMAIL", "all",
        r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b",
        1.0,
    ),

    # Aadhaar UID — 12 digits starting with 2-9, optional spaces/hyphens
    # between groups of 4.  Deliberately strict on the leading digit to
    # reduce false positives with arbitrary 12-digit numbers.
    (
        "AADHAAR_UID", "all",
        r"\b([2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4})\b",
        1.0,
    ),

    # PAN card — 5 uppercase letters, 4 digits, 1 uppercase letter.
    (
        "PAN_CARD", "all",
        r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b",
        1.0,
    ),

    # Indian postal (PIN) code — 6 digits, first digit 1-9.
    (
        "PIN_CODE", "all",
        r"\b([1-9][0-9]{5})\b",
        0.7,
    ),

    # Credit / debit card — 16 digits in 4 groups, optional space or hyphen.
    (
        "CREDIT_CARD", "all",
        r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b",
        1.0,
    ),

    # Indian passport — letter followed by 7 digits (e.g. A1234567).
    (
        "PASSPORT", "all",
        r"\b([A-Z][1-9][0-9]{6})\b",
        1.0,
    ),

    # Voter ID (EPIC) — 3 uppercase letters followed by 7 digits.
    (
        "VOTER_ID", "all",
        r"\b([A-Z]{3}[0-9]{7})\b",
        0.9,
    ),

    # IFSC code — 4 uppercase letters, literal 0, 6 alphanumeric chars.
    (
        "IFSC", "all",
        r"\b([A-Z]{4}0[A-Z0-9]{6})\b",
        0.9,
    ),
]


# ---------------------------------------------------------------------------
# 2. geo_library
#    SUFFIX  — location suffixes used for address-segment detection.
#    SAFE_CITY — well-known city names that should NOT be flagged as PII
#                addresses (prevents over-redaction of city mentions).
# ---------------------------------------------------------------------------

# fmt: off
_GEO_SUFFIXES: List[Tuple[str, str]] = [
    # (term_text, lang_code)

    # English
    ("nagar",     "en"), ("puram",    "en"), ("pur",      "en"),
    ("gram",      "en"), ("wadi",     "en"), ("ganj",     "en"),
    ("garh",      "en"), ("abad",     "en"), ("khand",    "en"),
    ("vihar",     "en"), ("colony",   "en"), ("sector",   "en"),
    ("enclave",   "en"), ("road",     "en"), ("marg",     "en"),
    ("street",    "en"), ("layout",   "en"), ("extension","en"),
    ("phase",     "en"), ("block",    "en"),

    # Hindi
    ("नगर",   "hi"), ("पुरम",  "hi"), ("पुर",    "hi"),
    ("ग्राम", "hi"), ("वाड़ी", "hi"), ("गंज",   "hi"),
    ("गढ़",   "hi"), ("आबाद",  "hi"), ("खंड",   "hi"),
    ("विहार", "hi"), ("कॉलोनी","hi"), ("मार्ग", "hi"),
    ("सेक्टर","hi"), ("एन्क्लेव","hi"),

    # Marathi
    ("नगर",   "mr"), ("पुरम",  "mr"), ("गाव",   "mr"),
    ("वाडी",  "mr"), ("पेठ",   "mr"), ("वस्ती", "mr"),
    ("कॉलनी", "mr"), ("रस्ता", "mr"), ("सेक्टर","mr"),

    # Tamil
    ("நகர்",    "ta"), ("புரம்",   "ta"), ("பட்டி",  "ta"),
    ("பாளையம்", "ta"), ("நகரம்",   "ta"), ("காலனி",  "ta"),
    ("தெரு",    "ta"), ("சாலை",    "ta"),
]

_SAFE_CITIES: List[Tuple[str, str]] = [
    # English — major Indian cities
    ("Mumbai",           "en"), ("Delhi",           "en"), ("Bangalore",       "en"),
    ("Bengaluru",        "en"), ("Chennai",         "en"), ("Kolkata",         "en"),
    ("Hyderabad",        "en"), ("Pune",            "en"), ("Ahmedabad",       "en"),
    ("Jaipur",           "en"), ("Lucknow",         "en"), ("Surat",           "en"),
    ("Kanpur",           "en"), ("Nagpur",          "en"), ("Indore",          "en"),
    ("Thane",            "en"), ("Bhopal",          "en"), ("Visakhapatnam",   "en"),
    ("Patna",            "en"), ("Vadodara",        "en"), ("Ghaziabad",       "en"),
    ("Ludhiana",         "en"), ("Agra",            "en"), ("Nashik",          "en"),
    ("Faridabad",        "en"), ("Meerut",          "en"), ("Rajkot",          "en"),
    ("Varanasi",         "en"), ("Srinagar",        "en"), ("Aurangabad",      "en"),
    ("Dhanbad",          "en"), ("Amritsar",        "en"), ("Prayagraj",       "en"),
    ("Allahabad",        "en"), ("Ranchi",          "en"), ("Coimbatore",      "en"),
    ("Jodhpur",          "en"), ("Madurai",         "en"), ("Raipur",          "en"),
    ("Kota",             "en"), ("Chandigarh",      "en"), ("Guwahati",        "en"),
    ("Thiruvananthapuram","en"),("Mysuru",          "en"), ("Bhubaneswar",     "en"),
    ("Salem",            "en"), ("Warangal",        "en"), ("Guntur",          "en"),
    ("Tiruchirappalli",  "en"), ("Kochi",           "en"), ("Vijayawada",      "en"),

    # Hindi script
    ("मुंबई",         "hi"), ("दिल्ली",       "hi"), ("बेंगलुरु",     "hi"),
    ("चेन्नई",        "hi"), ("कोलकाता",      "hi"), ("हैदराबाद",     "hi"),
    ("पुणे",          "hi"), ("अहमदाबाद",     "hi"), ("जयपुर",        "hi"),
    ("लखनऊ",          "hi"), ("सूरत",         "hi"), ("कानपुर",       "hi"),
    ("नागपुर",        "hi"), ("इंदौर",        "hi"), ("ठाणे",         "hi"),
    ("भोपाल",         "hi"), ("पटना",         "hi"), ("वडोदरा",       "hi"),
    ("आगरा",          "hi"), ("वाराणसी",      "hi"), ("अमृतसर",       "hi"),
    ("प्रयागराज",     "hi"), ("रांची",        "hi"), ("जोधपुर",       "hi"),
    ("रायपुर",        "hi"), ("कोटा",         "hi"), ("चंडीगढ़",      "hi"),
    ("गुवाहाटी",      "hi"), ("मैसूर",        "hi"), ("भुवनेश्वर",    "hi"),
    ("कोच्चि",        "hi"), ("विजयवाड़ा",    "hi"), ("नाशिक",        "hi"),

    # Marathi script
    ("मुंबई",     "mr"), ("पुणे",       "mr"), ("नागपूर",    "mr"),
    ("नाशिक",    "mr"), ("ठाणे",       "mr"), ("औरंगाबाद",  "mr"),
    ("सोलापूर",  "mr"), ("कोल्हापूर",  "mr"), ("अमरावती",   "mr"),
    ("जळगाव",   "mr"), ("अकोला",      "mr"), ("लातूर",     "mr"),
    ("दिल्ली",   "mr"), ("बेंगळुरू",   "mr"), ("हैदराबाद",  "mr"),
    ("अहमदाबाद", "mr"), ("जयपूर",      "mr"), ("सुरत",      "mr"),

    # Tamil script
    ("சென்னை",         "ta"), ("மும்பை",       "ta"), ("டெல்லி",        "ta"),
    ("பெங்களூரு",      "ta"), ("கொல்கத்தா",    "ta"), ("ஹைதராபாத்",    "ta"),
    ("புணே",           "ta"), ("அகமதாபாத்",    "ta"), ("சூரத்",         "ta"),
    ("கோயம்புத்தூர்",  "ta"), ("மதுரை",        "ta"), ("திருச்சிராப்பள்ளி", "ta"),
    ("சேலம்",          "ta"), ("திருவனந்தபுரம்","ta"), ("கொச்சி",       "ta"),
    ("விஜயவாடா",       "ta"), ("விசாகப்பட்டினம்","ta"),
]
# fmt: on


# ---------------------------------------------------------------------------
# 3. domain_policies  (8 domains, all inactive until explicitly activated)
# ---------------------------------------------------------------------------

def _logistics_rules() -> List[Dict]:
    """Core rules for all four logistics domains (language variant is a header concern)."""
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
        {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
        {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
        {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
        {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
        {"entity_type": "PERSON",      "action": "REDACT", "config": {}},
        {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}},
    ]


_DOMAINS: List[Tuple[str, str, List[Dict]]] = [
    # (domain_id, description, rules)

    (
        "general",
        "General — baseline PII for mixed content",
        [
            {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
            {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
            {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
            {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
            {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}},
        ],
    ),
    (
        "healthcare",
        "Healthcare — PHI, clinical codes, and common ID patterns",
        [
            {
                "entity_type": "PATIENT_CODE",
                "action": "REDACT_TAG",
                "config": {"tag_label": "[PATIENT_CODE]"},
                "custom_regex": r"\bHC-\d{4,8}\b",
            },
            {
                "entity_type": "MRN",
                "action": "REDACT_TAG",
                "config": {"tag_label": "[MRN]"},
                "custom_regex": r"\bMRN\s*[:#\-]?\s*\d{6,12}\b",
            },
            {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
            {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
            {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
            {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
            {"entity_type": "PERSON",      "action": "REDACT", "config": {}},
            {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}},
        ],
    ),
    (
        "financial",
        "Financial — payments and tax-related identifiers",
        [
            {"entity_type": "CREDIT_CARD", "action": "REDACT", "config": {}},
            {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
            {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
            {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
            {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
        ],
    ),
    (
        "education",
        "Education — student and institution context",
        [
            {"entity_type": "EMAIL",  "action": "REDACT", "config": {}},
            {"entity_type": "PHONE",  "action": "REDACT", "config": {}},
            {"entity_type": "PERSON", "action": "REDACT", "config": {}},
            {"entity_type": "PIN_CODE","action": "MASK",  "config": {"mask_char": "X"}},
        ],
    ),
    (
        "logistics",
        "Logistics — shipments, tracking references, vehicle plates, consignee PII (English)",
        _logistics_rules(),
    ),
    (
        "logistics_hindi",
        "Logistics — Hindi content; use header X-Language: hi with /redact",
        _logistics_rules(),
    ),
    (
        "logistics_tamil",
        "Logistics — Tamil content; use header X-Language: ta with /redact",
        _logistics_rules(),
    ),
    (
        "logistics_marathi",
        "Logistics — Marathi content; use header X-Language: mr with /redact",
        _logistics_rules(),
    ),
]


# ---------------------------------------------------------------------------
# Upgrade / downgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    conn = op.get_bind()

    # ---- pattern_library ---------------------------------------------------
    for entity_label, lang_code, regex_pattern, risk_score in _PATTERNS:
        conn.execute(
            sa.text(
                """
                INSERT INTO pattern_library (entity_label, lang_code, regex_pattern, risk_score, is_active)
                VALUES (:label, :lang, :pattern, :score, TRUE)
                ON CONFLICT (entity_label, lang_code) DO NOTHING
                """
            ),
            {"label": entity_label, "lang": lang_code, "pattern": regex_pattern, "score": risk_score},
        )

    # ---- geo_library -------------------------------------------------------
    for term_text, lang_code in _GEO_SUFFIXES:
        conn.execute(
            sa.text(
                """
                INSERT INTO geo_library (term_text, lang_code, term_type, is_active)
                VALUES (:term, :lang, 'SUFFIX', TRUE)
                ON CONFLICT DO NOTHING
                """
            ),
            {"term": term_text, "lang": lang_code},
        )

    for term_text, lang_code in _SAFE_CITIES:
        conn.execute(
            sa.text(
                """
                INSERT INTO geo_library (term_text, lang_code, term_type, is_active)
                VALUES (:term, :lang, 'SAFE_CITY', TRUE)
                ON CONFLICT DO NOTHING
                """
            ),
            {"term": term_text, "lang": lang_code},
        )

    # ---- domain_policies ---------------------------------------------------
    for domain_id, description, rules in _DOMAINS:
        existing = conn.execute(
            sa.text("SELECT 1 FROM domain_policies WHERE domain_id = :d LIMIT 1"),
            {"d": domain_id},
        ).first()
        if existing:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO domain_policies (domain_id, is_active, policy_json)
                VALUES (:domain_id, FALSE, CAST(:policy_json AS jsonb))
                """
            ),
            {"domain_id": domain_id, "policy_json": _policy(description, rules)},
        )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text(
        "DELETE FROM domain_policies WHERE domain_id IN ("
        "  'general','healthcare','financial','education',"
        "  'logistics','logistics_hindi','logistics_tamil','logistics_marathi'"
        ")"
    ))

    conn.execute(sa.text(
        "DELETE FROM geo_library WHERE term_type IN ('SUFFIX', 'SAFE_CITY')"
    ))

    conn.execute(sa.text(
        "DELETE FROM pattern_library WHERE entity_label IN ("
        "  'PHONE','EMAIL','AADHAAR_UID','PAN_CARD','PIN_CODE',"
        "  'CREDIT_CARD','PASSPORT','VOTER_ID','IFSC'"
        ")"
    ))
