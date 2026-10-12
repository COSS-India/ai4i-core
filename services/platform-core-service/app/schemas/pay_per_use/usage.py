"""Response schemas for the PPU usage dashboard."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.period import Period


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


class MonthlyQuota(BaseModel):
    """A task type's quota for the current billing month (quota_usage, the
    counter quota enforcement uses) — whatever period the dashboard shows."""
    billingMonth: str
    limit: float
    used: float
    remaining: float            # limit − used; negative when over quota
    percentageUsed: float


class CostShare(BaseModel):
    """One LLM token category in the Budget drill-down."""
    key: Literal["input", "cached_input", "output"]
    label: str
    units: float
    cost: float
    costShare: float            # share of PeriodUsage.cost


class PeriodUsage(BaseModel):
    """A task type's usage in the selected period (usage_events or
    daily_usage; see period_usage.period_source)."""
    units: float
    cost: float
    # LLM only (null otherwise): uncached input, cached input and output,
    # summing to units and cost; cached input is omitted when 0.
    breakdown: Optional[list[CostShare]] = None


class TaskTypeUsage(BaseModel):
    taskType: str
    unit: str
    # Current billing month; null when the institution has no quota for this
    # task type this month.
    quota: Optional[MonthlyQuota] = None
    periodUsage: PeriodUsage


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
    taskTypeCount: int          # distinct task types used in the period


class TenantHierarchicalItem(BaseModel):
    tenantId: str
    tenantName: str
    # Tier of the institution's most recent usage in the period (its current
    # tier when it has none).
    tier: str
    tierId: str
    currency: str
    # Spend in the selected period (usage_events / daily_usage).
    periodSpend: float
    # All-time balance: allocated budget vs all-time spend (budget_usage).
    budget: TenantBudget
    usage: TenantUsageCount
    tierBreakdown: list[TierUsageBreakdown]


class TenantHierarchicalListResponse(BaseModel):
    period: Period
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
    period: Period
    tenantId: str
    tenantName: str
    tier: str
    tierId: str
    currency: str
    periodSpend: float
    budget: TenantBudgetDetail
    usage: TenantUsageCount
    tierBreakdown: list[TierUsageBreakdown]
