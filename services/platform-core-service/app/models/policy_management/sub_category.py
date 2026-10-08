"""ORM model for the sub_category table."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.models import Base


class SubCategory(Base):
    """Grouping of policies within a category (e.g. 'PII Guardrails')."""

    __tablename__ = "sub_category"
    __table_args__ = (
        UniqueConstraint("name", name="uq_sub_category_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(
        Integer,
        ForeignKey("category.id", name="fk_sub_category_category_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, server_default=text("false"))

    category = relationship("Category", back_populates="sub_categories")
    policies = relationship("Policy", back_populates="sub_category")
