from pydantic import BaseModel , Field
from .enum_tenant import ServiceUnitType , ServiceCurrencyType
from decimal import Decimal
from typing import Dict , Any , Optional
from .service_create import ServiceResponse





class ServiceUpdateRequest(BaseModel):
    service_id : int
    price_per_unit: Optional[Decimal] = Field(None, gt=0)
    unit_type: Optional[ServiceUnitType] = None
    currency: Optional[ServiceCurrencyType] = None
    is_active: Optional[bool] = None


class FieldChange(BaseModel):
    old: Any
    new: Any


class ServiceUpdateResponse(BaseModel):
    message: str
    service: ServiceResponse
    changes: Dict[str, FieldChange]


