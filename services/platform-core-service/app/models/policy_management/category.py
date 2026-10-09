"""ORM model for the category table."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from app.models import Base


class Category(Base):
    """Top-level grouping of guardrail policies (e.g. 'Security & Privacy')."""

    __tablename__ = "category"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)

    # Case-insensitive uniqueness on name.
    __table_args__ = (
        Index("uq_category_name_lower", func.lower(name), unique=True),
    )

    sub_categories = relationship("SubCategory", back_populates="category")
