"""Response schemas for the Metering Dashboard's Applications tab."""
from typing import Literal

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
    # How much of the period periodSpend covers. Before usage was recorded,
    # spend is estimated from Prometheus, which can't tell an application's
    # keys apart when it has several: then those days' spend is the
    # application's (unattributedPeriodSpend), not any key's.
    #   full         every day of the period is in periodSpend
    #   partial      the estimated days aren't: periodSpend is the rest
    #   unavailable  the whole period is estimated days: periodSpend is 0
    periodSpendCoverage: Literal["full", "partial", "unavailable"] = "full"


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
    # Estimated spend in the period that no key can be given (see
    # ApiKeyUsageItem.periodSpendCoverage); part of periodSpend.
    unattributedPeriodSpend: float = 0
    totals: ApplicationUsageTotals
