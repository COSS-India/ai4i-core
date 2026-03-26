"""create pii guard tables and seed initial policies

Revision ID: 1a2b3c4d5e6f
Revises: e9c84005c25d
Create Date: 2026-03-24 23:01:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1a2b3c4d5e6f"
down_revision = "e9c84005c25d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pattern_library",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_label", sa.String(length=50), nullable=False),
        sa.Column("lang_code", sa.String(length=10), nullable=False),
        sa.Column("regex_pattern", sa.Text(), nullable=False),
        sa.Column("risk_score", sa.Float(), server_default="1.0", nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_label", "lang_code", name="uq_pattern_entity_lang"),
    )
    op.create_table(
        "geo_library",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("term_text", sa.String(length=100), nullable=False),
        sa.Column("lang_code", sa.String(length=10), nullable=False),
        sa.Column("term_type", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "keyword_library",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_text", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("lang_code", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "domain_policies",
        sa.Column("domain_id", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=True),
        sa.Column("policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("domain_id"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=50), nullable=True),
        sa.Column("domain_id", sa.String(length=50), nullable=True),
        sa.Column("target_context", sa.String(length=20), nullable=True),
        sa.Column("pii_count", sa.Integer(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    pattern_table = sa.table(
        "pattern_library",
        sa.column("entity_label", sa.String),
        sa.column("lang_code", sa.String),
        sa.column("regex_pattern", sa.Text),
    )
    op.bulk_insert(
        pattern_table,
        [
            {"entity_label": "AADHAAR_UID", "lang_code": "all", "regex_pattern": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"},
            {"entity_label": "PAN_CARD", "lang_code": "all", "regex_pattern": r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b"},
            {"entity_label": "PIN_CODE", "lang_code": "all", "regex_pattern": r"\b\d{3}\s?\d{3}\b"},
            {"entity_label": "PHONE", "lang_code": "all", "regex_pattern": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"},
            {"entity_label": "EMAIL", "lang_code": "all", "regex_pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"},
            {"entity_label": "CREDIT_CARD", "lang_code": "all", "regex_pattern": r"\b(?:\d[ -]*?){13,16}\b"},
            {
                "entity_label": "PERSON",
                "lang_code": "en",
                "regex_pattern": r"(?i)\b(?:Name|Mr\.|Ms\.|Mrs\.)\s+(?:is\s+)?[:\-]?\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)",
            },
            {
                "entity_label": "HOUSE_ANCHOR",
                "lang_code": "en",
                "regex_pattern": r"\b(?:Address|No\.|Flat|House|H\.No|Door|#|Plot|Tower|Wing|Floor|Villa|Apt)\s?[\w\d\-/.,]+\b",
            },
        ],
    )

    geo_table = sa.table(
        "geo_library",
        sa.column("term_text", sa.String),
        sa.column("lang_code", sa.String),
        sa.column("term_type", sa.String),
    )
    op.bulk_insert(
        geo_table,
        [
            {"term_text": "Road", "lang_code": "en", "term_type": "SUFFIX"},
            {"term_text": "Street", "lang_code": "en", "term_type": "SUFFIX"},
            {"term_text": "Nagar", "lang_code": "en", "term_type": "SUFFIX"},
            {"term_text": "Bangalore", "lang_code": "en", "term_type": "SAFE_CITY"},
        ],
    )

    keyword_table = sa.table(
        "keyword_library",
        sa.column("word_text", sa.String),
        sa.column("lang_code", sa.String),
        sa.column("category", sa.String),
    )
    op.bulk_insert(
        keyword_table,
        [
            {"word_text": "farmer", "lang_code": "en", "category": "OCCUPATION"},
            {"word_text": "male", "lang_code": "en", "category": "GENDER"},
        ],
    )


def downgrade():
    op.drop_table("audit_logs")
    op.drop_table("domain_policies")
    op.drop_table("keyword_library")
    op.drop_table("geo_library")
    op.drop_table("pattern_library")

