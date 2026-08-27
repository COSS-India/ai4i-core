import uuid

from sqlalchemy import Column, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class BudgetUsage(Base):
    __tablename__ = "budget_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id = Column(Integer, nullable=False, unique=True)
    api_key_budget_snap = Column(Numeric(15, 8), nullable=True)
    api_key_budget_used = Column(Numeric(15, 8), nullable=False, default=0, server_default="0")
