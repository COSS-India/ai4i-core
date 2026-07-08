from typing import List

from pydantic import BaseModel


class QuotaLimitUpdatedRequest(BaseModel):
    tier_name: str
    tenant_ids: List[str]
