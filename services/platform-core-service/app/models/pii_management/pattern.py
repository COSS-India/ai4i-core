"""ORM models for pii_pattern_library and pii_geo_library tables."""

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, UniqueConstraint

from app.models import Base


class PatternLibrary(Base):
    """
    Compiled regex patterns for PII entity detection, keyed by entity label and language.

    lang_code "all" is expanded by KnowledgeBaseService to [en, hi, mr, ta] at load time.
    Patterns with a unique (entity_label, lang_code) pair can be overridden per language.
    """

    __tablename__ = "pii_pattern_library"
    __table_args__ = (
        UniqueConstraint("entity_label", "lang_code", name="uq_pii_pattern_entity_lang"),
    )

    id             = Column(Integer, primary_key=True, autoincrement=True)
    entity_label   = Column(String(50), nullable=False)
    lang_code      = Column(String(10), nullable=False)   # "en" | "hi" | "mr" | "ta" | "all"
    regex_pattern  = Column(Text,       nullable=False)
    risk_score     = Column(Float,      server_default="1.0", nullable=True)
    is_active      = Column(Boolean,    server_default="true", nullable=True)


class GeoLibrary(Base):
    """
    Geographic reference terms used by the detection engine.

    term_type:
        SUFFIX   — location suffixes (nagar, puram, …) used to identify address segments.
        SAFE_CITY — well-known city names that should NOT be redacted as PII addresses.
    """

    __tablename__ = "pii_geo_library"

    id        = Column(Integer,    primary_key=True, autoincrement=True)
    term_text = Column(String(100), nullable=False)
    lang_code = Column(String(10),  nullable=False)
    term_type = Column(String(20),  nullable=False)   # "SUFFIX" | "SAFE_CITY"
    is_active = Column(Boolean,    server_default="true", nullable=True)
