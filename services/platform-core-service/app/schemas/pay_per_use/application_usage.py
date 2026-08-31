"""Response schemas for the Metering Dashboard's Applications tab."""
from pydantic import BaseModel


class MoneyPercent(BaseModel):
    amount: float
    percentage: float


class ApplicationUsageSummaryResponse(BaseModel):
    totalApplications: int
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent


class ApplicationUsageListItem(BaseModel):
    applicationId: int
    name: str
    domain: str | None = None
    # allocatedBudget.percentage is % of the institution's total budget.
    # spendBudget/remainingBudget.percentage are % of this application's OWN allocation.
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent


class ApplicationUsageListResponse(BaseModel):
    data: list[ApplicationUsageListItem]
    total: int


class ApiKeyUsageItem(BaseModel):
    keyId: int
    keyName: str
    maskedKey: str
    isActive: bool
    # allocatedBudget.percentage is % of the institution's total budget, computed
    # from the amount — NOT the raw api_key.allocated_percentage column, which is
    # stored as % of the parent APPLICATION's budget instead (see
    # application_usage_service.py's get_application_detail for why the two must
    # not be conflated under this one field).
    # spendBudget/remainingBudget.percentage are % of this key's OWN allocation.
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent


class ApplicationUsageTotals(BaseModel):
    allocatedBudget: float
    spendBudget: float
    remainingBudget: float


class ApplicationUsageDetailResponse(BaseModel):
    applicationId: int
    applicationName: str
    domain: str | None = None
    allocatedBudget: MoneyPercent
    spendBudget: MoneyPercent
    remainingBudget: MoneyPercent
    apiKeys: list[ApiKeyUsageItem]
    totals: ApplicationUsageTotals
