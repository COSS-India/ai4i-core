"""Response models for GET /pricing-summary (tier costs grouped by model task type)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TierPricingDetail(BaseModel):
    service_id: str = Field(..., description="Service row UUID")
    service_name: str
    cost_per_unit: float
    unit_type: str


class PricingSummaryRow(BaseModel):
    task_type: str
    unit_type: str
    tier_1: Optional[TierPricingDetail] = None
    tier_2: Optional[TierPricingDetail] = None
