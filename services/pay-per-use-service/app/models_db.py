import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    api_key_id = Column(String(64), nullable=False, index=True)
    service_id = Column(String(128), nullable=False, index=True)
    units_consumed = Column(Numeric(20, 6), nullable=False)
    cost = Column(Numeric(20, 6), nullable=False)
    rate_used = Column(Numeric(20, 8), nullable=True)
    tier = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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


class QuotaUsage(Base):
    __tablename__ = "quota_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(64), nullable=False, index=True)
    service_id = Column(String(128), nullable=False, index=True)
    period = Column(String(16), nullable=False)
    requests_used = Column(Integer, nullable=False, default=0)
    units_used = Column(Numeric(20, 6), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
