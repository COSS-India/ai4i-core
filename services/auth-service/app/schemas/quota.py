from typing import List, Optional

from pydantic import BaseModel


class QuotaLimitUpdatedRequest(BaseModel):
    tier_name: str
    # tier_id is the source of truth going forward: the sender
    # (platform-core-service) can no longer compute tenant_ids itself now that
    # ppu_tenant_tier_assignments is dropped (tier assignment lives only on
    # auth-service's own tenants.tier_id), so it hands over the tier and lets
    # notify_quota_limit_updated resolve affected tenants here instead.
    # tenant_ids stays as an accepted fallback — defaulted, not required — so an
    # old platform-core-service build mid-rollout that still sends only
    # tier_name/tenant_ids doesn't 422 against a new auth-service.
    tier_id: Optional[str] = None
    tenant_ids: List[str] = []
