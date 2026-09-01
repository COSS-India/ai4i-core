"""Response schemas for the PPU usage dashboard."""
from datetime import datetime
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
    # No spend/percentage here (and never one) — ppu_quota_usage has no per-task-type
    # money column; real spend only exists at the tenant-total level, sourced from
    # budget_usage.api_key_budget_used (see UsageSummaryResponse.totalSpend).


class UsageSummaryResponse(BaseModel):
    # None (all-time) rather than a sentinel string like "lifetime": billing_period on
    # this and the other /usage-* routes is validated against
    # ^\d{4}-(0[1-9]|1[0-2])$, which "lifetime" would fail — a client that reads this
    # value and echoes it back as billing_period (e.g. into /usage-tenant) must get a
    # value that round-trips, and omitting the param is how all-time is requested there
    # too. application_usage_service's own ApplicationUsageSummaryResponse.billingPeriod
    # is NOT the same case: those routes declare no billing_period param at all, so
    # its "lifetime" constant can never be fed back into a query string.
    billingPeriod: Optional[str] = None
    # Real, tenant-total spend (sum of budget_usage.api_key_budget_used across every
    # tenant in scope) — always lifetime-cumulative, since budget_usage carries no
    # per-month dimension (see UsageService.get_summary / get_tenant_budgets).
    totalSpend: float
    currency: str
    activeTenants: int
    budgetExceededTenants: int
    # No spendChangePercent (month-over-month spend delta) here, and never one —
    # budget_usage (where real spend lives) has no per-month breakdown to compare
    # against; this isn't "not yet populated," it's structurally uncomputable, so
    # it's not a field at all rather than a permanently-null one (see
    # UsageService.get_summary's docstring).
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
    # No spend/percentage here (and never one) — see SpendItem's docstring; the same
    # "no per-task-type money column" limitation applies at this tier/task-type
    # breakdown level too.


class TierUsageBreakdown(BaseModel):
    tierId: str
    tierName: str
    taskTypes: list[TaskTypeUsage]
    # No spend here either — budget_usage (where real spend lives) has no tier_id
    # dimension, so per-tier cost isn't real data any more than per-task-type is.


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
    # Real, tenant-total spend — sum of budget_usage.api_key_budget_used across this
    # tenant's api keys, always lifetime-cumulative (see TierUsageBreakdown's
    # docstring for why this can't be broken down by tier/task type).
    spend: float
    budget: TenantBudget
    usage: TenantUsageCount
    tierBreakdown: list[TierUsageBreakdown]


class TenantHierarchicalListResponse(BaseModel):
    data: list[TenantHierarchicalItem]
    total: int


class TenantBudgetDetail(TenantBudget):
    """TenantBudget plus the tenant's configured budget window — used only by
    /usage-tenant, not /usage-tenants (see TenantUsageDetailResponse). Sourced from
    tenants.budget_effective_from/to (auth-service), set once at tenant creation and
    untouched by budget top-up/top-down — null for a tenant with no configured
    window (see UsageRepository.get_tenant_budgets)."""
    budgetEffectiveFrom: Optional[datetime] = None
    budgetEffectiveTo: Optional[datetime] = None


class TenantUsageDetailResponse(BaseModel):
    """Response for /usage-tenant — identical shape to TenantHierarchicalItem except
    budget carries the extra effective-from/to window (see TenantBudgetDetail)."""
    tenantId: str
    tenantName: str
    tier: str
    tierId: str
    currency: str
    spend: float
    budget: TenantBudgetDetail
    usage: TenantUsageCount
    tierBreakdown: list[TierUsageBreakdown]
