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
    helper: Optional[str] = None       # optional dynamic sub-text (e.g. "97.40% success rate")


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
    task_types: Optional[list[str]] = None


class ServiceRow(BaseModel):
    service: str
    requests: int
    native_units: float = 0.0
    native_unit_suffix: str
    success_pct: float
    failure_rate_pct: float = 0.0       # 100 - success_pct


class TenantRow(BaseModel):
    rank: int
    tenant: str
    organisation: Optional[str] = None
    requests: int
    formatted_requests: str
    percentage: float


class OthersData(BaseModel):
    count: int
    requests: int
    percentage: float


class UsageConcentration(BaseModel):
    top_tenants: list[TenantRow]
    others: OthersData
    top_concentration_pct: float
    grand_total: int


class PlatformAdoption(BaseModel):
    total_tenants: Optional[int] = None
    new_tenants_7d: Optional[int] = None
    active_24h: Optional[int] = None
    active_7d: Optional[int] = None
    active_30d: Optional[int] = None


class ServiceEntry(BaseModel):
    display_name: str
    requests: int
    formatted_requests: str
    percentage: float = 0.0       # this service's share of the tenant's total (row %)


class TenantServiceRow(BaseModel):
    rank: int
    tenant: str
    services: dict[str, ServiceEntry]
    total: int
    formatted_total: str
    percentage: float = 0.0       # this tenant's share of all tenants' total (grand %)


class MostUsedService(BaseModel):
    service: Optional[str] = None
    requests: int = 0


class HighestFailureService(BaseModel):
    service: Optional[str] = None
    failure_rate_pct: float = 0.0


class ServiceSummary(BaseModel):
    """Service Consumption KPI cards (computed over services with traffic)."""
    most_used: Optional[MostUsedService] = None
    highest_failure_rate: Optional[HighestFailureService] = None


# ── Tab responses ────────────────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    scope: Scope
    kpis: list[Cell]
    platform_adoption: Optional[PlatformAdoption] = None
    usage_concentration: Optional[UsageConcentration] = None
    request_volume: Optional[Graph] = None
    degraded: bool = False
    generated_at: str


class TenantConsumptionResponse(BaseModel):
    scope: Scope
    avg_requests_per_tenant: Optional[Cell] = None   # KPI card shown above the ranking
    tenant_ranking: list[TenantRow]
    usage_by_service: list[TenantServiceRow]
    degraded: bool = False
    generated_at: str


class ServiceConsumptionResponse(BaseModel):
    scope: Scope
    summary: Optional[ServiceSummary] = None
    service_breakdown: list[ServiceRow]
    degraded: bool = False
    generated_at: str
