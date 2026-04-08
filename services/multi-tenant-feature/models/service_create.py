from pydantic import BaseModel , Field
from .enum_tenant import (
    ServiceUnitType,
    SubscriptionType,
    ServiceCurrencyType,
    BillingUnitType,
    ServiceTier,
)
from decimal import Decimal
from datetime import datetime
from typing import List, Optional

class ServiceCreateRequest(BaseModel):
    service_name: SubscriptionType = Field(..., example="asr")
    unit_type: ServiceUnitType
    price_per_unit: Decimal = Field(..., gt=0)
    currency: ServiceCurrencyType = Field(default="INR")
    is_active: bool
    cost_per_unit: Optional[Decimal] = Field(None, gt=0, description="Pay-per-use cost; defaults to price_per_unit when omitted")
    tier: Optional[ServiceTier] = None
    billing_unit_type: Optional[BillingUnitType] = Field(
        None, description="Billing unit: minutes, characters, or requests"
    )



class ServiceResponse(BaseModel):
    id: int
    service_name: str
    unit_type: ServiceUnitType
    price_per_unit: Decimal
    currency: ServiceCurrencyType
    is_active: bool
    cost_per_unit: Optional[Decimal] = None
    tier: Optional[str] = None
    billing_unit_type: Optional[str] = None
    created_at: datetime | None
    updated_at: datetime | None



class ListServicesResponse(BaseModel):
    count: int
    services: List[ServiceResponse]