"""ORM model for the policy table."""

import enum

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship

from app.models import Base


class GuardrailScope(str, enum.Enum):
    """Which side of a model call a policy is enforced on."""

    INPUT = "input"
    OUTPUT = "output"
    BOTH = "both"


class Policy(Base):
    __tablename__ = "policy"
    __table_args__ = (
        UniqueConstraint("policy_id", name="uq_policy_policy_id"),
        UniqueConstraint("name", name="uq_policy_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    domain = Column(ARRAY(Text), nullable=False)
    guardrail_scope = Column(
        Enum(
            GuardrailScope,
            name="guardrail_scope_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    is_global = Column(Boolean, nullable=False, server_default=text("false"))
    sub_category_id = Column(
        Integer,
        ForeignKey("sub_category.id", name="fk_policy_sub_category_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, server_default=text("false"))
    # Elements reference policy_type.id; not enforced by the database.
    policy_type_id = Column(ARRAY(Integer), nullable=True)

    sub_category = relationship("SubCategory", back_populates="policies")
