from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    tenant_id: str
    api_key_id: str
    service_id: str
    estimated_units: float = Field(..., ge=0)


class CheckResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None


class RecordRequest(BaseModel):
    tenant_id: str
    api_key_id: str
    service_id: str
    units_consumed: float = Field(..., ge=0)


class RecordResponse(BaseModel):
    recorded: bool
    cost: float
    remaining_balance: float


class TopUpRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)


class UsageAdopterResponse(BaseModel):
    total_tenants: int = 0
    total_cost: float = 0.0
    tenants: List[Dict[str, Any]] = []


class TenantUsageResponse(BaseModel):
    total_requests: int = 0
    total_cost: float = 0.0
    remaining_balance: float = 0.0
    remaining_quota: Dict[str, Any] = {}
    usage_by_service: List[Dict[str, Any]] = []
    api_key_breakdown: List[Dict[str, Any]] = []
