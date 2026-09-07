from typing import List

from pydantic import BaseModel, ConfigDict, Field

_QUOTA_LIMIT_UPDATED_REQUEST_EXAMPLE = {
    "tier_name": "Standard",
    "tenant_ids": ["<place your id here>"],
}


class QuotaLimitUpdatedRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_QUOTA_LIMIT_UPDATED_REQUEST_EXAMPLE]})

    tier_name: str
    tenant_ids: List[str] = Field(
        ..., description="Tenant IDs affected by this tier's quota-limit change. Replace the example values with real tenant IDs from your system."
    )
