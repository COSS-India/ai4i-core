"""ORM model for the category table."""

from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from app.models import Base


class Category(Base):
    """Top-level grouping of guardrail policies (e.g. 'Security & Privacy')."""

    __tablename__ = "category"
    __table_args__ = (
        UniqueConstraint("name", name="uq_category_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("false"))

    sub_categories = relationship("SubCategory", back_populates="category")
