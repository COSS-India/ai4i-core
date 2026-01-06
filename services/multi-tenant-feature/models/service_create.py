from pydantic import BaseModel , Field
from .enum_tenant import ServiceUnitType , SubscriptionType , ServiceCurrencyType
from decimal import Decimal
from datetime import datetime
from typing import List

class ServiceCreateRequest(BaseModel):
    service_name: SubscriptionType = Field(..., example="asr")
    unit_type: ServiceUnitType
    price_per_unit: Decimal = Field(..., gt=0)
    currency: ServiceCurrencyType = Field(default="INR")
    is_active: bool



class ServiceResponse(BaseModel):
    id: int
    service_name: str
    unit_type: ServiceUnitType
    price_per_unit: Decimal
    currency: ServiceCurrencyType
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None



class ListServicesResponse(BaseModel):
    count: int
    services: List[ServiceResponse]