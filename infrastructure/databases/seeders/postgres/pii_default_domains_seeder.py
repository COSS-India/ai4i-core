"""
PII Default Domains Seeder

Seeds default PII patterns, geo terms, and domain policies into ai4i_platform.

Schema (ai4i_platform):
  pattern_library  — regex patterns per entity label and language
  geo_library      — address suffixes and safe city names per language
  domain_policies  — named domains with JSON rules blob
"""

import json
from infrastructure.databases.core.base_seeder import BaseSeeder


# (entity_label, lang_code, regex_pattern)
_PATTERNS = [
    # ── Universal patterns (all languages) ──────────────────────────────────
    ("EMAIL",        "all", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ("PHONE",        "all", r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"),
    ("AADHAAR_UID",  "all", r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
    ("PAN_CARD",     "all", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    ("PIN_CODE",     "all", r"\b[1-9][0-9]{5}\b"),
    ("CREDIT_CARD",  "all", r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
    # Healthcare
    ("PATIENT_CODE", "all", r"\bHC-\d{4,8}\b"),
    ("MRN",          "all", r"\bMRN\s*[:#\-]?\s*\d{6,12}\b"),
    # Logistics
    ("TRACKING_ID",  "all", r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b"),
    ("COURIER_REF",  "all", r"\b1Z[0-9A-Z]{16}\b"),
    ("VEHICLE_REG",  "all", r"\b[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{1,3}\s?[0-9]{4}\b"),

    # ── Language-specific PERSON patterns (capture group 1 for name span) ───
    ("PERSON", "en", r"(?i)\b(?:Name|Mr\.|Ms\.|Mrs\.)\s+(?:is\s+)?[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)"),
    ("PERSON", "hi", r"(?:\s|^)(?:नाम|इसम)\s*[:\-]?\s*([\wऀ-ॿ]+(?:\s[\wऀ-ॿ]+)*)"),
    ("PERSON", "mr", r"(?:\s|^)(?:नाव)\s*[:\-]?\s*([\wऀ-ॿ]+(?:\s[\wऀ-ॿ]+)*)"),
    ("PERSON", "ta", r"(?:\s|^)(?:பெயர்)\s*[:\-]?\s*([\w஀-௿]+(?:\s[\w஀-௿]+)*)"),

    # ── Language-specific HOUSE_ANCHOR patterns ──────────────────────────────
    ("HOUSE_ANCHOR", "en", r"\b(?:Address|No\.|Flat|House|H\.No|Door|#|Plot|Tower|Wing|Floor|Villa|Apt)\s?[\w\d\-/.,]+\b"),
    ("HOUSE_ANCHOR", "hi", r"(?:\s|^)(?:पता|मकान|घर|प्लॉट|फ्लैट|नंबर|संख्या|टावर|विला|भवन|विंग)\s?[\w\d\-/.,]+(?:\s|$)"),
    ("HOUSE_ANCHOR", "mr", r"(?:\s|^)(?:घर|सदन|निवास|इमारत|फ्लॅट|अपार्टमेंट|नंबर|क्रमांक|चाळ|खोली|गाळा)\s?[\w\d\-/.,]+(?:\s|$)"),
    ("HOUSE_ANCHOR", "ta", r"(?:\s|^)(?:வீடு|வீட்டு|எண்|மனை|தளம்|கதவு|பிளாட்|டவர்|வில்லா)\s?[\w\d\-/.,]+(?:\s|[.,]|$)"),
]


# (term_text, lang_code, term_type)
_GEO_DATA = [
    # English — address suffixes
    ("Road",       "en", "SUFFIX"), ("Street",    "en", "SUFFIX"), ("Nagar",    "en", "SUFFIX"),
    ("Colony",     "en", "SUFFIX"), ("Cross",     "en", "SUFFIX"), ("Main",     "en", "SUFFIX"),
    ("Block",      "en", "SUFFIX"), ("Layout",    "en", "SUFFIX"),
    # English — safe cities (well-known, suppress aggressive redaction)
    ("Bangalore",  "en", "SAFE_CITY"), ("Mumbai",    "en", "SAFE_CITY"), ("Delhi",      "en", "SAFE_CITY"),
    ("Chennai",    "en", "SAFE_CITY"), ("Pune",      "en", "SAFE_CITY"), ("Hyderabad",  "en", "SAFE_CITY"),
    ("Koramangala","en", "SAFE_CITY"),
    # Hindi — address suffixes
    ("रोड",        "hi", "SUFFIX"), ("नगर",       "hi", "SUFFIX"), ("मार्ग",     "hi", "SUFFIX"),
    ("चौक",        "hi", "SUFFIX"),
    # Hindi — safe cities
    ("बैंगलोर",    "hi", "SAFE_CITY"), ("मुंबई",     "hi", "SAFE_CITY"), ("दिल्ली",    "hi", "SAFE_CITY"),
    ("कोरमंगला",  "hi", "SAFE_CITY"),
    # Marathi — address suffixes
    ("रोड",        "mr", "SUFFIX"), ("मार्ग",      "mr", "SUFFIX"), ("नगर",       "mr", "SUFFIX"),
    ("पेठ",        "mr", "SUFFIX"), ("आळी",        "mr", "SUFFIX"), ("वाडा",       "mr", "SUFFIX"),
    ("गल्ली",      "mr", "SUFFIX"),
    # Marathi — safe cities
    ("पुणे",       "mr", "SAFE_CITY"), ("मुंबई",    "mr", "SAFE_CITY"), ("नागपूर",    "mr", "SAFE_CITY"),
    # Tamil — address suffixes
    ("சாலை",       "ta", "SUFFIX"), ("தெரு",       "ta", "SUFFIX"), ("நகர்",       "ta", "SUFFIX"),
    # Tamil — safe cities
    ("சென்னை",     "ta", "SAFE_CITY"), ("பெங்களூரு", "ta", "SAFE_CITY"), ("மதுரை",    "ta", "SAFE_CITY"),
]


def _redact(et, label=None):
    return {"entity_type": et, "action": "REDACT_TAG", "config": {"tag_label": label or f"[{et}]"}}

def _mask(et):
    return {"entity_type": et, "action": "MASK", "config": {"mask_char": "X"}}

def _hash(et):
    return {"entity_type": et, "action": "HASH", "config": {}}


# (domain_id, description, is_active, rules)
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
        "government",
        "Citizen data services",
        False,
        [_redact("AADHAAR_UID"), _redact("PAN_CARD"), _redact("PERSON"), _redact("EMAIL"), _redact("PHONE")],
    ),
    (
        "employment",
        "HR and payroll context",
        False,
        [_redact("PERSON", "[EMPLOYEE]"), _redact("EMAIL"), _redact("PHONE"),
         _redact("AADHAAR_UID"), _redact("PAN_CARD")],
    ),
    (
        "digital",
        "Digital identity and online services",
        False,
        [_redact("EMAIL"), _redact("PHONE"), _redact("PERSON")],
    ),
    # ── Logistics domains (active — service falls back to 'logistics') ───────
    (
        "logistics",
        "Shipments, tracking references, vehicle plates, consignee PII (English)",
        True,
        [_redact("PERSON", "[NAME]"), _redact("LOCATION", "[LOC]"), _redact("HOUSE_ANCHOR", "[ADDRESS]"),
         _redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"),
         _redact("EMAIL"), _hash("PHONE"), _redact("AADHAAR_UID"), _redact("PAN_CARD"), _mask("PIN_CODE")],
    ),
    (
        "logistics_hindi",
        "Logistics domain for Hindi content — use X-Language: hi with /redact",
        True,
        [_redact("PERSON", "[नाम]"), _redact("LOCATION", "[स्थान]"), _redact("HOUSE_ANCHOR", "[घर नंबर]"),
         _redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"),
         _redact("EMAIL", "[ईमेल]"), _hash("PHONE"), _redact("AADHAAR_UID"), _mask("PIN_CODE")],
    ),
    (
        "logistics_marathi",
        "Logistics domain for Marathi content — use X-Language: mr with /redact",
        True,
        [_redact("PERSON", "[नाव]"), _redact("LOCATION", "[स्थान]"), _redact("HOUSE_ANCHOR", "[घर क्रमांक]"),
         _redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"),
         _redact("EMAIL", "[ईमेल]"), _hash("PHONE"), _mask("PIN_CODE")],
    ),
    (
        "logistics_tamil",
        "Logistics domain for Tamil content — use X-Language: ta with /redact",
        True,
        [_redact("PERSON", "[பெயர்]"), _redact("LOCATION", "[முகவரி]"), _redact("HOUSE_ANCHOR", "[வீட்டு எண்]"),
         _redact("TRACKING_ID"), _redact("COURIER_REF"), _redact("VEHICLE_REG"),
         _redact("EMAIL", "[மின்னஞ்சல்]"), _hash("PHONE"), _mask("PIN_CODE")],
    ),
]


class PiiDefaultDomainsSeeder(BaseSeeder):
    """Seed default PII patterns, geo terms, and domain policies into ai4i_platform."""

    database = "ai4i_platform"

    def run(self, adapter):
        existing = adapter.fetch_one("SELECT COUNT(*) FROM domain_policies")
        if existing and existing[0] > 0:
            print("    ⚠ PII domain policies already exist, skipping")
            return

        for entity_label, lang_code, regex in _PATTERNS:
            adapter.execute(
                """
                INSERT INTO pattern_library (entity_label, lang_code, regex_pattern, risk_score, is_active)
                VALUES (:label, :lang, :regex, 1.0, true)
                ON CONFLICT ON CONSTRAINT uq_pattern_entity_lang DO NOTHING
                """,
                {"label": entity_label, "lang": lang_code, "regex": regex},
            )
        print(f"    ✓ Seeded {len(_PATTERNS)} PII patterns into pattern_library")

        for term_text, lang_code, term_type in _GEO_DATA:
            adapter.execute(
                """
                INSERT INTO geo_library (term_text, lang_code, term_type, is_active)
                VALUES (:term, :lang, :type, true)
                """,
                {"term": term_text, "lang": lang_code, "type": term_type},
            )
        print(f"    ✓ Seeded {len(_GEO_DATA)} geo terms into geo_library")

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
