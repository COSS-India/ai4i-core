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
    # (either the caller passed one `task_types` value, or only one type has usage this
    # period) — different task types use incompatible units (tokens/characters/images/
    # minutes), so these are null rather than a nonsensical cross-unit sum whenever more
    # than one type is in play. tokenUnit names the unit these three figures are in.
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
    # Flat convenience mirrors of budget.limit/remaining and usage.quotaLimit/consumed/
    # remaining, named identically to UsageSummaryResponse's totals so the same "Total
    # allocated / used / remaining" summary-card component can read one field set
    # whether it's showing the platform-wide (admin) or a single tenant's (tenant admin)
    # totals. Token fields follow the same single-task-type gating as usage.quotaLimit —
    # null when the tenant has more than one task type in scope this period.
    totalAllocatedBudget: float = 0
    totalRemainingBudget: float = 0
    tokenUnit: Optional[str] = None
    totalUsedTokens: Optional[float] = None
    totalAllocatedTokens: Optional[float] = None
    totalRemainingTokens: Optional[float] = None


class TenantHierarchicalListResponse(BaseModel):
    data: list[TenantHierarchicalItem]
    total: int
