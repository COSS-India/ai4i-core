"""Response schemas for the PPU usage dashboard."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.period import Period


class QuotaUsageItem(BaseModel):
    """One task type's quota usage in the summary's billing month."""
    modelTaskType: str
    unit: str
    # Units used in the billing month (ppu_quota_usage), summed across tenants.
    consumption: float
    # Quota allocated for this task type, summed across tenants' CURRENT tier only
    # (a grant resets on reassignment, it isn't cumulative) — None when no tenant in
    # scope has a quota snapshot for it. Same unit as consumption.
    allocated: Optional[float] = None
    # No money here: ppu_quota_usage has no per-task-type money column; spend only
    # exists per institution, in SummaryBudget.


class SummaryBudget(BaseModel):
    """Budget across institutions — all-time, never scoped by billing_period.

    budget_usage is a running total with no month dimension, so spend and the
    balance are lifetime figures. Covers every institution with a budget on file
    (tenants.allocated_budget set), whether or not it has quota rows, so
    institutions on untiered keys count too; DEACTIVATED institutions are left out.
    """
    basis: Literal["all_time"] = "all_time"
    institutions: int           # institutions with a budget on file, in scope
    allocated: float            # sum of their allocated budgets
    spent: float                # sum of their lifetime spend (budget_usage)
    remaining: float            # allocated − spent; negative when overspent overall
    # Institutions whose lifetime spend has reached their budget (spent >= budget,
    # the same rule billing uses to block a key); a zero budget doesn't count.
    exceededTenants: int


class SummaryQuota(BaseModel):
    """Quota usage — one billing month (all months when billingMonth is null)."""
    basis: Literal["billing_month", "all_time"]
    # The billing_period requested; null when omitted (all months up to now). Null
    # rather than a sentinel string, so echoing it back as billing_period works.
    billingMonth: Optional[str] = None
    # Institutions with quota usage in scope.
    activeTenants: int
    byTaskType: list[QuotaUsageItem]


class UsageSummaryResponse(BaseModel):
    """Key metrics strip: budget (all-time) and quota (monthly), kept apart because
    they have different time bases — billing_period scopes quota only."""
    currency: str
    budget: SummaryBudget
    quota: SummaryQuota


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
