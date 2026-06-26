"""Response schemas for the PPU usage dashboard."""
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
    spendByModelTaskType: list[SpendItem]


class TenantUsageBreakdown(BaseModel):
    modelTaskType: str
    consumptionToDate: float
    unit: str
    spend: float


class TenantUsageItem(BaseModel):
    tenantId: str
    tenantName: str
    tier: str
    budgetLimit: float
    spendToDate: float
    remainingBudget: float
    quotaLimit: float
    quotaUnit: str
    consumptionToDate: float
    remainingQuota: float
    currency: str


class TenantUsageListResponse(BaseModel):
    data: list[TenantUsageItem]
    total: int


class TenantUsageDetailResponse(TenantUsageItem):
    breakdown: list[TenantUsageBreakdown]
