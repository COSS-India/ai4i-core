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
    spendByModelTaskType: list[SpendItem]


class TenantUsageBreakdown(BaseModel):
    modelTaskType: str
    consumptionToDate: float
    unit: str
    spend: float
    quotaLimit: Optional[float]
    remainingQuota: Optional[float]


class TenantUsageItem(BaseModel):
    tenantId: str
    tenantName: str
    tier: str
    budgetLimit: float
    spendToDate: float
    remainingBudget: float
    quotaLimit: Optional[float]
    quotaUnit: str
    consumptionToDate: Optional[float]
    remainingQuota: Optional[float]
    currency: str


class TenantUsageListResponse(BaseModel):
    data: list[TenantUsageItem]
    total: int


class TenantUsageDetailResponse(TenantUsageItem):
    breakdown: list[TenantUsageBreakdown]
