"""ORM model for the domain_policies table (PII database)."""

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.pii_management import PiiBase


class DomainPolicy(PiiBase):
    """
    A named redaction policy domain (e.g. 'logistics', 'healthcare').

    policy_json structure:
        {
            "meta": {"version": "1.0", "description": "..."},
            "rules": [
                {
                    "entity_type": "PHONE",
                    "action": "REDACT_TAG" | "MASK" | "REDACT",
                    "config": {"tag_label": "[PHONE]"} | {"mask_char": "X"} | {},
                    "custom_regex": "optional pattern"   # omit to use pattern_library
                },
                ...
            ]
        }
    """

    __tablename__ = "domain_policies"

    domain_id  = Column(String(50), primary_key=True)
    is_active  = Column(Boolean,   server_default="false", nullable=True)
    policy_json = Column(JSONB,    nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=True)
