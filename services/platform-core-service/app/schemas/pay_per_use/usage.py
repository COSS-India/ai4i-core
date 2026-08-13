"""Response schemas for the PPU usage dashboard."""
from typing import Optional

from pydantic import BaseModel


class SpendItem(BaseModel):
    modelTaskType: str
    unit: str
    consumption: float
    spend: float
    percentage: float


class UsageSummaryResponse(BaseModel):
    billingPeriod: str
    totalSpend: float
    currency: str
    activeTenants: int
    budgetExceededTenants: int
    spendChangePercent: Optional[float] = None
    spendByModelTaskType: list[SpendItem]
    # Money totals: always computable (single currency, one INR figure per tenant),
    # summed across every tenant with a budget assignment covering this billing_month
    # (see PPUUsageService.get_summary / _resolve_budget's has_budget).
    totalAllocatedBudget: float = 0
    totalRemainingBudget: float = 0
    # Token totals: only meaningful when the response is scoped to a single task type
    # (either the caller passed one `task_types` value, or only one type actually had
    # usage this period) — different task types use incompatible units (tokens/
    # characters/images/minutes), so these stay null otherwise rather than a
    # nonsensical cross-unit sum. tokenUnit names the unit these three figures are in.
    # (See PPUUsageService.get_summary for where these are computed and why
    # "one type had usage" — not "the allowlist has one entry" — is the real signal.)
    tokenUnit: Optional[str] = None
    totalUsedTokens: Optional[float] = None
    totalAllocatedTokens: Optional[float] = None
    totalRemainingTokens: Optional[float] = None


class TaskTypeUsage(BaseModel):
    taskType: str
    unit: str
    quotaLimit: Optional[float] = None
    consumed: float
    remaining: Optional[float] = None
    percentage: float
    spend: float


class TierUsageBreakdown(BaseModel):
    tierId: str
    tierName: str
    spend: float
    taskTypes: list[TaskTypeUsage]


class TenantBudget(BaseModel):
    limit: float
    spent: float
    remaining: float
    percentageUsed: float


class TenantUsageCount(BaseModel):
    taskTypeCount: int
    unit: Optional[str] = None
    quotaLimit: Optional[float] = None
    consumed: Optional[float] = None
    remaining: Optional[float] = None
    percentage: Optional[float] = None


class TenantHierarchicalItem(BaseModel):
    tenantId: str
    tenantName: str
    tier: str
    tierId: str
    currency: str
    spend: float
    budget: TenantBudget
    usage: TenantUsageCount
    tierBreakdown: list[TierUsageBreakdown]


class TenantHierarchicalListResponse(BaseModel):
    data: list[TenantHierarchicalItem]
    total: int
