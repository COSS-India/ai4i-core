"""add pii tables to core db

Moves PII management tables into ai4iplatform_core (previously they lived in
the separate ai4i_platform database).  Table names carry the pii_ prefix to
co-exist cleanly with mm_* and alert_* tables.

Revision ID: b9e3f1a2c4d5
Revises: 7d2f9a4e1c08
Create Date: 2026-05-29

Note: re-parented from 31d7bc3f4379 onto 7d2f9a4e1c08 (add_alert_tables) to
linearize the two ai4iplatform_core heads that both branched off 31d7bc3f4379.
Both are additive and order-independent; this makes `alembic upgrade head`
unambiguous so the deploy migration job can run.

"""

from __future__ import annotations

import json
from typing import Dict, List, Tuple, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b9e3f1a2c4d5"
down_revision: Union[str, None] = "7d2f9a4e1c08"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Seed helpers  (same data as the old ai4i_platform_db seed migration)
# ---------------------------------------------------------------------------

def _policy(description: str, rules: List[Dict]) -> str:
    return json.dumps(
        {"meta": {"version": "1.0", "description": description}, "rules": rules},
        separators=(",", ":"),
    )


_PATTERNS: List[Tuple[str, str, str, float]] = [
    ("PHONE",       "all", r"(?:(?:\+?91|0)[\s\-]?)?([6-9]\d{9})\b",             1.0),
    ("EMAIL",       "all", r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b", 1.0),
    ("AADHAAR_UID", "all", r"\b([2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4})\b",          1.0),
    ("PAN_CARD",    "all", r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b",                    1.0),
    ("PIN_CODE",    "all", r"\b([1-9][0-9]{5})\b",                                0.7),
    ("CREDIT_CARD", "all", r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b",  1.0),
    ("PASSPORT",    "all", r"\b([A-Z][1-9][0-9]{6})\b",                           1.0),
    ("VOTER_ID",    "all", r"\b([A-Z]{3}[0-9]{7})\b",                             0.9),
    ("IFSC",        "all", r"\b([A-Z]{4}0[A-Z0-9]{6})\b",                         0.9),
]

_GEO_SUFFIXES: List[Tuple[str, str]] = [
    # English
    ("nagar","en"),("puram","en"),("pur","en"),("gram","en"),("wadi","en"),
    ("ganj","en"),("garh","en"),("abad","en"),("khand","en"),("vihar","en"),
    ("colony","en"),("sector","en"),("enclave","en"),("road","en"),("marg","en"),
    ("street","en"),("layout","en"),("extension","en"),("phase","en"),("block","en"),
    # Hindi
    ("नगर","hi"),("पुरम","hi"),("पुर","hi"),("ग्राम","hi"),("वाड़ी","hi"),
    ("गंज","hi"),("गढ़","hi"),("आबाद","hi"),("खंड","hi"),("विहार","hi"),
    ("कॉलोनी","hi"),("मार्ग","hi"),("सेक्टर","hi"),("एन्क्लेव","hi"),
    # Marathi
    ("नगर","mr"),("पुरम","mr"),("गाव","mr"),("वाडी","mr"),("पेठ","mr"),
    ("वस्ती","mr"),("कॉलनी","mr"),("रस्ता","mr"),("सेक्टर","mr"),
    # Tamil
    ("நகர்","ta"),("புரம்","ta"),("பட்டி","ta"),("பாளையம்","ta"),
    ("நகரம்","ta"),("காலனி","ta"),("தெரு","ta"),("சாலை","ta"),
]

_SAFE_CITIES: List[Tuple[str, str]] = [
    # English
    ("Mumbai","en"),("Delhi","en"),("Bangalore","en"),("Bengaluru","en"),
    ("Chennai","en"),("Kolkata","en"),("Hyderabad","en"),("Pune","en"),
    ("Ahmedabad","en"),("Jaipur","en"),("Lucknow","en"),("Surat","en"),
    ("Kanpur","en"),("Nagpur","en"),("Indore","en"),("Thane","en"),
    ("Bhopal","en"),("Visakhapatnam","en"),("Patna","en"),("Vadodara","en"),
    ("Ghaziabad","en"),("Ludhiana","en"),("Agra","en"),("Nashik","en"),
    ("Faridabad","en"),("Meerut","en"),("Rajkot","en"),("Varanasi","en"),
    ("Srinagar","en"),("Aurangabad","en"),("Dhanbad","en"),("Amritsar","en"),
    ("Prayagraj","en"),("Allahabad","en"),("Ranchi","en"),("Coimbatore","en"),
    ("Jodhpur","en"),("Madurai","en"),("Raipur","en"),("Kota","en"),
    ("Chandigarh","en"),("Guwahati","en"),("Thiruvananthapuram","en"),
    ("Mysuru","en"),("Bhubaneswar","en"),("Salem","en"),("Warangal","en"),
    ("Guntur","en"),("Tiruchirappalli","en"),("Kochi","en"),("Vijayawada","en"),
    # Hindi
    ("मुंबई","hi"),("दिल्ली","hi"),("बेंगलुरु","hi"),("चेन्नई","hi"),
    ("कोलकाता","hi"),("हैदराबाद","hi"),("पुणे","hi"),("अहमदाबाद","hi"),
    ("जयपुर","hi"),("लखनऊ","hi"),("सूरत","hi"),("कानपुर","hi"),
    ("नागपुर","hi"),("इंदौर","hi"),("ठाणे","hi"),("भोपाल","hi"),
    ("पटना","hi"),("वडोदरा","hi"),("आगरा","hi"),("वाराणसी","hi"),
    ("अमृतसर","hi"),("प्रयागराज","hi"),("रांची","hi"),("जोधपुर","hi"),
    ("रायपुर","hi"),("कोटा","hi"),("चंडीगढ़","hi"),("गुवाहाटी","hi"),
    ("मैसूर","hi"),("भुवनेश्वर","hi"),("कोच्चि","hi"),("विजयवाड़ा","hi"),("नाशिक","hi"),
    # Marathi
    ("मुंबई","mr"),("पुणे","mr"),("नागपूर","mr"),("नाशिक","mr"),("ठाणे","mr"),
    ("औरंगाबाद","mr"),("सोलापूर","mr"),("कोल्हापूर","mr"),("अमरावती","mr"),
    ("जळगाव","mr"),("अकोला","mr"),("लातूर","mr"),("दिल्ली","mr"),
    ("बेंगळुरू","mr"),("हैदराबाद","mr"),("अहमदाबाद","mr"),("जयपूर","mr"),("सुरत","mr"),
    # Tamil
    ("சென்னை","ta"),("மும்பை","ta"),("டெல்லி","ta"),("பெங்களூரு","ta"),
    ("கொல்கத்தா","ta"),("ஹைதராபாத்","ta"),("புணே","ta"),("அகமதாபாத்","ta"),
    ("சூரத்","ta"),("கோயம்புத்தூர்","ta"),("மதுரை","ta"),("திருச்சிராப்பள்ளி","ta"),
    ("சேலம்","ta"),("திருவனந்தபுரம்","ta"),("கொச்சி","ta"),
    ("விஜயவாடா","ta"),("விசாகப்பட்டினம்","ta"),
]


def _logistics_rules() -> List[Dict]:
    return [
        {"entity_type": "TRACKING_ID", "action": "REDACT_TAG", "config": {"tag_label": "[TRACKING]"},
         "custom_regex": r"\b(?:AWB|TRACK(?:ING)?|LR|CONNOTE)\s*[:]?\s*[A-Z0-9][A-Z0-9\-]{5,24}\b"},
        {"entity_type": "COURIER_REF",  "action": "REDACT_TAG", "config": {"tag_label": "[REF]"},
         "custom_regex": r"\b1Z[0-9A-Z]{16}\b"},
        {"entity_type": "VEHICLE_REG",  "action": "REDACT_TAG", "config": {"tag_label": "[VEHICLE]"},
         "custom_regex": r"\b[A-Z]{2}\s?[0-9]{1,2}\s?[A-Z]{1,3}\s?[0-9]{4}\b"},
        {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
        {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
        {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
        {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
        {"entity_type": "PERSON",      "action": "REDACT", "config": {}},
        {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}},
    ]


_DOMAINS: List[Tuple[str, str, List[Dict]]] = [
    ("general",           "General — baseline PII for mixed content",
     [{"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
      {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
      {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
      {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
      {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}}]),

    ("healthcare",        "Healthcare — PHI, clinical codes, and common ID patterns",
     [{"entity_type": "PATIENT_CODE", "action": "REDACT_TAG", "config": {"tag_label": "[PATIENT_CODE]"},
       "custom_regex": r"\bHC-\d{4,8}\b"},
      {"entity_type": "MRN",          "action": "REDACT_TAG", "config": {"tag_label": "[MRN]"},
       "custom_regex": r"\bMRN\s*[:#\-]?\s*\d{6,12}\b"},
      {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
      {"entity_type": "PHONE",       "action": "REDACT", "config": {}},
      {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
      {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
      {"entity_type": "PERSON",      "action": "REDACT", "config": {}},
      {"entity_type": "PIN_CODE",    "action": "MASK",   "config": {"mask_char": "X"}}]),

    ("financial",         "Financial — payments and tax-related identifiers",
     [{"entity_type": "CREDIT_CARD", "action": "REDACT", "config": {}},
      {"entity_type": "PAN_CARD",    "action": "REDACT", "config": {}},
      {"entity_type": "AADHAAR_UID", "action": "REDACT", "config": {}},
      {"entity_type": "EMAIL",       "action": "REDACT", "config": {}},
      {"entity_type": "PHONE",       "action": "REDACT", "config": {}}]),

    ("education",         "Education — student and institution context",
     [{"entity_type": "EMAIL",   "action": "REDACT", "config": {}},
      {"entity_type": "PHONE",   "action": "REDACT", "config": {}},
      {"entity_type": "PERSON",  "action": "REDACT", "config": {}},
      {"entity_type": "PIN_CODE","action": "MASK",   "config": {"mask_char": "X"}}]),

    ("logistics",         "Logistics — English content",        _logistics_rules()),
    ("logistics_hindi",   "Logistics — Hindi content (X-Language: hi)",   _logistics_rules()),
    ("logistics_tamil",   "Logistics — Tamil content (X-Language: ta)",   _logistics_rules()),
    ("logistics_marathi", "Logistics — Marathi content (X-Language: mr)", _logistics_rules()),
]


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── 1. Create tables ──────────────────────────────────────────────────

    op.create_table(
        "pii_domain_policies",
        sa.Column("domain_id",   sa.String(50),  primary_key=True),
        sa.Column("is_active",   sa.Boolean(),   server_default=sa.text("false"), nullable=True),
        sa.Column("policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at",  sa.DateTime(),  server_default=sa.text("current_timestamp"), nullable=True),
    )

    op.create_table(
        "pii_pattern_library",
        sa.Column("id",            sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("entity_label",  sa.String(50),   nullable=False),
        sa.Column("lang_code",     sa.String(10),   nullable=False),
        sa.Column("regex_pattern", sa.Text(),        nullable=False),
        sa.Column("risk_score",    sa.Float(),       server_default=sa.text("1.0"), nullable=True),
        sa.Column("is_active",     sa.Boolean(),    server_default=sa.text("true"), nullable=True),
        sa.UniqueConstraint("entity_label", "lang_code", name="uq_pii_pattern_entity_lang"),
    )

    op.create_table(
        "pii_geo_library",
        sa.Column("id",        sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("term_text", sa.String(100),  nullable=False),
        sa.Column("lang_code", sa.String(10),   nullable=False),
        sa.Column("term_type", sa.String(20),   nullable=False),
        sa.Column("is_active", sa.Boolean(),    server_default=sa.text("true"), nullable=True),
    )

    op.create_table(
        "pii_tenant_domain_map",
        sa.Column("tenant_id",  sa.String(255), primary_key=True),
        sa.Column("domain_id",  sa.String(50),  nullable=False),
        sa.Column("created_at", sa.DateTime(),  server_default=sa.text("current_timestamp"), nullable=True),
        sa.Column("updated_at", sa.DateTime(),  server_default=sa.text("current_timestamp"), nullable=True),
    )

    # pii_audit_logs is also created by the older policy_db migration
    # (eeb2648f856c); after the "PII into primary DB" consolidation both target
    # the same physical DB, so guard against the duplicate to stay idempotent.
    if "pii_audit_logs" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "pii_audit_logs",
            sa.Column("id",             sa.Integer(),                    primary_key=True, autoincrement=True),
            sa.Column("trace_id",       postgresql.UUID(as_uuid=False),  nullable=True),
            sa.Column("tenant_id",      sa.String(50),                   nullable=True),
            sa.Column("domain_id",      sa.String(50),                   nullable=True),
            sa.Column("target_context", sa.String(20),                   nullable=True),
            sa.Column("pii_count",      sa.Integer(),                    nullable=True),
            sa.Column("processing_ms",  sa.Integer(),                    nullable=True),
            sa.Column("trace_json",     postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at",     sa.DateTime(),                   server_default=sa.text("current_timestamp"), nullable=True),
        )

    # ── 2. Seed pattern_library ───────────────────────────────────────────
    conn = op.get_bind()

    for entity_label, lang_code, regex_pattern, risk_score in _PATTERNS:
        conn.execute(
            sa.text("""
                INSERT INTO pii_pattern_library (entity_label, lang_code, regex_pattern, risk_score, is_active)
                VALUES (:label, :lang, :pattern, :score, TRUE)
                ON CONFLICT ON CONSTRAINT uq_pii_pattern_entity_lang DO NOTHING
            """),
            {"label": entity_label, "lang": lang_code, "pattern": regex_pattern, "score": risk_score},
        )

    # ── 3. Seed geo_library ───────────────────────────────────────────────
    for term_text, lang_code in _GEO_SUFFIXES:
        existing = conn.execute(
            sa.text("SELECT 1 FROM pii_geo_library WHERE term_text=:t AND lang_code=:l AND term_type='SUFFIX' LIMIT 1"),
            {"t": term_text, "l": lang_code},
        ).first()
        if not existing:
            conn.execute(
                sa.text("INSERT INTO pii_geo_library (term_text, lang_code, term_type, is_active) VALUES (:t, :l, 'SUFFIX', TRUE)"),
                {"t": term_text, "l": lang_code},
            )

    for term_text, lang_code in _SAFE_CITIES:
        existing = conn.execute(
            sa.text("SELECT 1 FROM pii_geo_library WHERE term_text=:t AND lang_code=:l AND term_type='SAFE_CITY' LIMIT 1"),
            {"t": term_text, "l": lang_code},
        ).first()
        if not existing:
            conn.execute(
                sa.text("INSERT INTO pii_geo_library (term_text, lang_code, term_type, is_active) VALUES (:t, :l, 'SAFE_CITY', TRUE)"),
                {"t": term_text, "l": lang_code},
            )

    # ── 4. Seed domain_policies ───────────────────────────────────────────
    for domain_id, description, rules in _DOMAINS:
        existing = conn.execute(
            sa.text("SELECT 1 FROM pii_domain_policies WHERE domain_id = :d LIMIT 1"),
            {"d": domain_id},
        ).first()
        if existing:
            continue
        conn.execute(
            sa.text("""
                INSERT INTO pii_domain_policies (domain_id, is_active, policy_json)
                VALUES (:domain_id, FALSE, CAST(:policy_json AS jsonb))
            """),
            {"domain_id": domain_id, "policy_json": _policy(description, rules)},
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # pii_audit_logs is also owned by the older policy_db migration
    # (eeb2648f856c); only drop it here if the upgrade actually created it,
    # mirroring the guarded create above. Otherwise leave it to its owner.
    op.drop_table("pii_tenant_domain_map")
    op.drop_table("pii_geo_library")
    op.drop_table("pii_pattern_library")
    op.drop_table("pii_domain_policies")
