"""ORM model for the sub_category table."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from app.models import Base


class SubCategory(Base):
    """Grouping of policies within a category (e.g. 'PII Guardrails')."""

    __tablename__ = "sub_category"

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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=func.now())
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)

    # Case-insensitive uniqueness on name.
    __table_args__ = (
        Index("uq_sub_category_name_lower", func.lower(name), unique=True),
    )

    category = relationship("Category", back_populates="sub_categories")
    policies = relationship("Policy", back_populates="sub_category")
