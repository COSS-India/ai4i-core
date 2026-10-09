"""ORM model for the policy_type table."""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base


class PolicyType(Base):
    """A kind of policy and the configurable fields it exposes."""

    __tablename__ = "policy_type"
    __table_args__ = (
        UniqueConstraint("policy_type", name="uq_policy_type_policy_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_type = Column(String(100), nullable=False)
    policy_fields = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
