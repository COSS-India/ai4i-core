import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class BudgetUsage(Base):
    __tablename__ = "budget_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id = Column(Integer, nullable=False, unique=True)
    api_key_budget_snap = Column(Numeric(15, 2), nullable=True)
    api_key_budget_used = Column(Numeric(15, 2), nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
