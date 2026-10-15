"""Response schemas for the Metering Dashboard's Applications tab."""
from pydantic import BaseModel

from app.schemas.period import Period


class MoneyPercent(BaseModel):
    amount: float
    percentage: float


class ApplicationUsageSummaryResponse(BaseModel):
    period: Period
    totalApplications: int
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent
    # Spend in the selected period (usage_events / daily_usage); percentage is
    # of the institution's budget.
    periodSpend: MoneyPercent
    # Describes spendBudget/remainingBudget only: always the constant
    # "lifetime", since they come from budget_usage, which has no time
    # dimension. periodSpend is the period-scoped figure.
    billingPeriod: str = "lifetime"


class ApplicationUsageListItem(BaseModel):
    applicationId: int
    name: str
    domain: str | None = None
    # allocatedBudget.percentage is % of the institution's total budget.
    # spendBudget/remainingBudget (all-time) and periodSpend (the selected
    # period) percentages are % of this application's OWN allocation.
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent
    periodSpend: MoneyPercent


class ApplicationUsageListResponse(BaseModel):
    period: Period
    data: list[ApplicationUsageListItem]
    total: int


class ApiKeyUsageItem(BaseModel):
    keyId: int
    keyName: str
    maskedKey: str
    isActive: bool
    # allocatedBudget.percentage is % of the parent application's budget,
    # computed from the amount (see application_usage_service.py's
    # get_application_detail).
    # spendBudget/remainingBudget (all-time) and periodSpend (the selected
    # period) percentages are % of this key's OWN allocation.
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent
    periodSpend: MoneyPercent


class ApplicationUsageTotals(BaseModel):
    allocatedBudget: float
    spendBudget: float
    remainingBudget: float
    periodSpend: float


class ApplicationUsageDetailResponse(BaseModel):
    period: Period
    applicationId: int
    applicationName: str
    domain: str | None = None
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent
    periodSpend: MoneyPercent
    apiKeys: list[ApiKeyUsageItem]
    # False when part of periodSpend can't be split between the API keys:
    # usage backfilled from Prometheus (daily_usage source 'backfill') has no
    # key when the application has several. The keys' periodSpend then leaves
    # it out, and the drawer shows a dash for them instead.
    keySpendAvailable: bool = True
    totals: ApplicationUsageTotals
