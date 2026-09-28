from typing import List

from pydantic import BaseModel, Field

class TierReactivatedRequest(BaseModel):
    tier_id: str = Field(..., description="UUID of the reactivated tier.")
    tenant_ids: List[int] = Field(..., description="Tenant IDs currently assigned to this tier.")
