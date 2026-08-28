from typing import List

from pydantic import BaseModel, ConfigDict

_QUOTA_LIMIT_UPDATED_REQUEST_EXAMPLE = {
    "tier_name": "Standard",
    "tenant_ids": ["<place your id here>"],
}


class QuotaLimitUpdatedRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": _QUOTA_LIMIT_UPDATED_REQUEST_EXAMPLE})

    tier_name: str
    tenant_ids: List[str]
