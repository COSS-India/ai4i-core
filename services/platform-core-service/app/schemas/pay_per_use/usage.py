"""Response schemas for the PPU usage dashboard."""
from typing import Optional

from pydantic import BaseModel


class SpendItem(BaseModel):
    modelTaskType: str
    unit: str
    consumption: float
    spend: float
    percentage: float


class TokenTotalsMixin(BaseModel):
    """Shared by UsageSummaryResponse (platform-wide) and TenantHierarchicalItem
    (single tenant) so both expose identical field names — one frontend summary-card
    component can read either response the same way, whether it's showing admin or
    tenant-admin totals.

    Money totals (totalAllocatedBudget/totalRemainingBudget) are always computable
    (single currency), summed across every tenant/assignment with a budget covering
    this billing_month (see PPUUsageService._resolve_budget's has_budget).

    Token totals (tokenUnit/totalUsedTokens/totalAllocatedTokens/totalRemainingTokens)
    are only meaningful when scoped to a single task type — either the caller passed
    one `task_types` value, or only one type has usage this period. Different task
    types use incompatible units (tokens/characters/images/minutes), so these are null
    rather than a nonsensical cross-unit sum whenever more than one type is in play.
    tokenUnit names the unit the three token figures are in.
    """
    totalAllocatedBudget: float = 0
    totalRemainingBudget: float = 0
    tokenUnit: Optional[str] = None
    totalUsedTokens: Optional[float] = None
    totalAllocatedTokens: Optional[float] = None
    totalRemainingTokens: Optional[float] = None


class UsageSummaryResponse(TokenTotalsMixin):
    billingPeriod: str
    totalSpend: float
    currency: str
    activeTenants: int
    budgetExceededTenants: int
    spendChangePercent: Optional[float] = None
    spendByModelTaskType: list[SpendItem]


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


class TenantHierarchicalItem(TokenTotalsMixin):
    """totalAllocatedBudget/totalRemainingBudget mirror budget.limit/remaining;
    totalUsedTokens/totalAllocatedTokens/totalRemainingTokens mirror
    usage.consumed/quotaLimit/remaining — see TokenTotalsMixin for the shared gating
    rule these six fields follow.
    """
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
