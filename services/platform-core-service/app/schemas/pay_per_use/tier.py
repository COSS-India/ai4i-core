from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.enums.model_management import resolve_task_type


class TierQuotaIn(BaseModel):
    modelTaskType: str = Field(..., min_length=1)
    # Ceiling is the largest integer TierQuota.monthly_quota's Numeric(15, 4)
    # column can store exactly (11 integer digits), so an out-of-range limit is
    # rejected here instead of persisting and breaking on read-back.
    limit: int = Field(..., ge=0, le=99_999_999_999)

    @field_validator("modelTaskType", mode="before")
    @classmethod
    def normalize_model_task_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return resolve_task_type(v)
        return v


class TierQuotaOut(BaseModel):
    modelTaskType: str
    limit: int
    pendingLimit: Optional[int] = None

    model_config = {"from_attributes": True}


def _check_duplicate_model_task_types(quotas: List[TierQuotaIn]) -> List[TierQuotaIn]:
    seen = set()
    for q in quotas:
        if q.modelTaskType in seen:
            raise ValueError(f"Duplicate modelTaskType '{q.modelTaskType}' in quotas")
        seen.add(q.modelTaskType)
    return quotas


_TIER_CREATE_EXAMPLE = {
    "name": "Standard",
    "description": "Standard monthly quota tier for translation and speech services",
    "quotas": [
        {"modelTaskType": "nmt", "limit": 100000},
        {"modelTaskType": "asr", "limit": 50000},
    ],
}


class TierCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_TIER_CREATE_EXAMPLE]})

    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    quotas: List[TierQuotaIn] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_unique_quotas(self):
        _check_duplicate_model_task_types(self.quotas)
        return self


_TIER_UPDATE_EXAMPLE = {
    "tier_id": "<place your uuid here>",
    "name": "Standard",
    "description": "Updated quota tier for translation and speech services",
    "quotas": [
        {"modelTaskType": "nmt", "limit": 150000},
    ],
}


class TierUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_TIER_UPDATE_EXAMPLE]})

    tier_id: str = Field(..., description="UUID of the tier to update")
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    quotas: Optional[List[TierQuotaIn]] = None
    cancel_pending_quota: Optional[List[str]] = None

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


class ListTiersResponse(BaseModel):
    """GET /pay-per-use/tiers

    Note: this endpoint's own ``{data, total}`` shape — not the
    ``{success, data, meta}`` envelope used by the tenant-assignment routes
    in this same file — matching what ``tier_service.list_tiers`` actually
    returns.
    """

    data: List[TierOut]
    total: int
