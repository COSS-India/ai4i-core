from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class TierQuotaIn(BaseModel):
    modelTaskType: str = Field(..., min_length=1)
    limit: int = Field(..., ge=0)


class TierQuotaOut(BaseModel):
    modelTaskType: str
    limit: int

    model_config = {"from_attributes": True}


def _check_duplicate_model_task_types(quotas: List[TierQuotaIn]) -> List[TierQuotaIn]:
    seen = set()
    for q in quotas:
        if q.modelTaskType in seen:
            raise ValueError(f"Duplicate modelTaskType '{q.modelTaskType}' in quotas")
        seen.add(q.modelTaskType)
    return quotas


class TierCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    quotas: List[TierQuotaIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_quotas(self):
        _check_duplicate_model_task_types(self.quotas)
        return self


class TierUpdate(BaseModel):
    tier_id: str = Field(..., description="UUID of the tier to update")
    name: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    quotas: Optional[List[TierQuotaIn]] = None

    @model_validator(mode="after")
    def validate_unique_quotas(self):
        if self.quotas:
            _check_duplicate_model_task_types(self.quotas)
        return self


class TierOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    quotas: List[TierQuotaOut] = []
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    model_config = {"from_attributes": True}
