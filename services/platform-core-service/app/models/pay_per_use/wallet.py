import uuid

from sqlalchemy import Column, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.models import Base


class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, unique=True, index=True)
    balance = Column(Numeric(20, 6), nullable=False, default=0)
    total_plan_cost = Column(Numeric(20, 6), nullable=False, default=0)
    total_used = Column(Numeric(20, 6), nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="INR")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    amount = Column(Numeric(20, 6), nullable=False)
    type = Column(String(16), nullable=False)
    reference_id = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
