"""
ORM models for policy-service.
Aligned with the PII Policy Module API spec.
Imported in app/db/base.py so metadata.create_all covers all tables.
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import AppDBBase as Base


class PiiType(Base):
    """
    pii_types – reusable PII entity definitions.
    mask_format is mutable and can be updated via API.
    """
    __tablename__ = "pii_types"
    __table_args__ = (
        UniqueConstraint("pii_type_label", name="uq_pii_type_label"),
    )

    pii_type_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pii_type_label = Column(String(255), nullable=False, index=True)
    regex_pattern = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    mask_format = Column(String(32), nullable=False)          # full | partial | redact
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # relationships
    policy_links = relationship(
        "PolicyPiiType", back_populates="pii_type", cascade="all, delete-orphan"
    )


class PiiPolicy(Base):
    """
    pii_policy – domain-scoped sanitisation policies.
    """
    __tablename__ = "pii_policy"

    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_global = Column(Boolean, nullable=False, default=False, server_default="false")
    supported_languages = Column(JSONB, nullable=False, default=list)  # ["en","hi"]
    tenant_ids = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationships
    pii_types = relationship(
        "PolicyPiiType", back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyPiiType(Base):
    """
    policy_pii_types – join table linking policies to PII types.
    """
    __tablename__ = "policy_pii_types"
    __table_args__ = (
        UniqueConstraint("policy_id", "pii_type_id", name="uq_policy_pii_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pii_policy.policy_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pii_type_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pii_types.pii_type_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # relationships
    policy = relationship("PiiPolicy", back_populates="pii_types")
    pii_type = relationship("PiiType", back_populates="policy_links")
