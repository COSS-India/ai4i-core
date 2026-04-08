from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class TierEnum(str, Enum):
    TIER_1 = "Tier-1"
    TIER_2 = "Tier-2"
    TIER_3 = "Tier-3"


class ServiceLimitItem(BaseModel):
    service_type: str = Field(..., min_length=1)
    unit_type: str = Field(..., min_length=1)
    limit_value: int = Field(..., ge=0)


# --- Quota ---
class QuotaConfigCreate(BaseModel):
    name: str = Field(..., min_length=1)
    requests_per_hour: int = Field(..., ge=0)
    service_limits: List[ServiceLimitItem] = Field(default_factory=list)


class QuotaConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    requests_per_hour: Optional[int] = Field(None, ge=0)
    service_limits: Optional[List[ServiceLimitItem]] = None


class QuotaServiceLimitOut(BaseModel):
    service_type: str
    unit_type: str
    limit_value: int

    model_config = {"from_attributes": True}


class QuotaConfigOut(BaseModel):
    id: UUID
    name: str
    requests_per_hour: int
    service_limits: List[QuotaServiceLimitOut]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Rate limit ---
class RateLimitConfigCreate(BaseModel):
    name: str = Field(..., min_length=1)
    requests_per_hour_per_api_key: int = Field(..., ge=0)
    requests_per_hour_per_tenant: int = Field(..., ge=0)


class RateLimitConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    requests_per_hour_per_api_key: Optional[int] = Field(None, ge=0)
    requests_per_hour_per_tenant: Optional[int] = Field(None, ge=0)


class RateLimitConfigOut(BaseModel):
    id: UUID
    name: str
    requests_per_hour_per_api_key: int
    requests_per_hour_per_tenant: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PlanServiceOut(BaseModel):
    service_id: str
    service_name: str
    unit_type: str
    cost_per_unit: float
    tier: str


class PlanCreateRequest(BaseModel):
    plan_name: str = Field(..., min_length=1)
    cost: Decimal = Field(default=Decimal("100.00"), ge=Decimal("0"))
    tier: TierEnum


class PlanOut(BaseModel):
    id: UUID
    plan_name: str
    cost: Decimal
    tier: str
    quota_config: Dict[str, Any]
    rate_limit_config: Dict[str, Any]

    model_config = {"from_attributes": True}

    @field_serializer("cost")
    def _serialize_cost(self, v: Decimal) -> float:
        return float(v)


class PlanUpdateRequest(BaseModel):
    plan_name: Optional[str] = Field(None, min_length=1)
    cost: Optional[Decimal] = Field(None, ge=Decimal("0"))
    tier: Optional[TierEnum] = None
