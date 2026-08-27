"""Response schemas for the PPU usage dashboard."""
from typing import Optional

from pydantic import BaseModel


class SpendItem(BaseModel):
    modelTaskType: str
    unit: str
    consumption: float
    # Quota allocated for this task type this billing_month, summed across tenants'
    # CURRENT tier only (see UsageService.get_summary) — None when no tenant in
    # scope has a quota snapshot for it. consumption is the used-side counterpart,
    # already in the same unit; a per-type field generalizes to any number of task
    # types in scope (unlike a single flat total, which can only ever hold one unit).
    allocated: Optional[float] = None
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
    # (see UsageService.get_summary / _resolve_budget's has_budget).
    totalAllocatedBudget: float = 0
    totalRemainingBudget: float = 0


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
