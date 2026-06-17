"""Response schemas for the metering dashboard tabs."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class Cell(BaseModel):
    """Uniform KPI card shape."""
    key: str
    label: str
    value: Any
    previous: Optional[Any] = None
    pct_change: Optional[float] = None


class GraphPoint(BaseModel):
    ts: int
    value: float


class GraphSeries(BaseModel):
    key: str
    label: str
    points: list[GraphPoint]


class Graph(BaseModel):
    step: str
    series: list[GraphSeries]


class Scope(BaseModel):
    role: str
    tenant_id: Optional[str] = None
    organisation: Optional[str] = None
    window: str


class ServiceRow(BaseModel):
    service: str
    metering_unit: str
    requests: int
    native_units: Optional[float] = None
    native_unit_suffix: str
    success_pct: float
    failed: int
    vs_prev_period_pct: Optional[float] = None


class TenantRow(BaseModel):
    rank: int
    tenant: str
    organisation: Optional[str] = None
    requests: int
    formatted_requests: str
    percentage: float


class UsageConcentration(BaseModel):
    top_tenants: list[TenantRow]
    others: dict
    top_concentration_pct: float
    grand_total: int


class ThroughputData(BaseModel):
    avg_rps: float
    peak_rps: Optional[float] = None
    peak_at: Optional[str] = None


# ── Tab responses ────────────────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    scope: Scope
    kpis: list[Cell]
    active_tenants: list[Cell]
    platform_adoption: Optional[UsageConcentration] = None
    usage_concentration: Optional[UsageConcentration] = None
    request_volume: Optional[Graph] = None
    throughput: ThroughputData
    degraded: bool = False
    generated_at: str


class TenantConsumptionResponse(BaseModel):
    scope: Scope
    tenant_ranking: list[TenantRow]
    usage_by_service: list[dict]
    degraded: bool = False
    generated_at: str


class ServiceConsumptionResponse(BaseModel):
    scope: Scope
    service_breakdown: list[ServiceRow]
    throughput: ThroughputData
    request_volume: Optional[Graph] = None
    degraded: bool = False
    generated_at: str
