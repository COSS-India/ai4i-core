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
    activeTenants: int
    budgetExceededTenants: int
    budgetExceededChangePercent: Optional[float] = None
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
