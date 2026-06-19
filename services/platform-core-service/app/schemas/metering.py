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
    percentage: float = 0.0             # share of total requests (Service Consumption donut)
    native_units: Optional[float] = None
    native_unit_suffix: str
    success_pct: float
    failure_rate_pct: float = 0.0       # 100 - success_pct
    failed: int
    vs_prev_period_pct: Optional[float] = None


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


class TenantServiceRow(BaseModel):
    rank: int
    tenant: str
    services: dict[str, ServiceEntry]
    total: int
    formatted_total: str


class ThroughputData(BaseModel):
    avg_rps: float
    peak_rps: Optional[float] = None
    peak_at: Optional[str] = None


class RequestHealth(BaseModel):
    """Total / successful / failed request counts + rates (Request Volume & Health card)."""
    total: int
    successful: int
    failed: int
    total_formatted: str
    successful_formatted: str
    failed_formatted: str
    success_rate_pct: float
    failure_rate_pct: float


class MostUsedService(BaseModel):
    service: Optional[str] = None
    requests: int = 0


class HighestFailureService(BaseModel):
    service: Optional[str] = None
    failure_rate_pct: float = 0.0


class ServiceSummary(BaseModel):
    """Service Consumption KPI cards (computed over services with traffic)."""
    active_services: int = 0
    most_used: Optional[MostUsedService] = None
    highest_failure_rate: Optional[HighestFailureService] = None


# ── Tab responses ────────────────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    scope: Scope
    kpis: list[Cell]
    active_tenants: list[Cell]
    platform_adoption: Optional[PlatformAdoption] = None
    usage_concentration: Optional[UsageConcentration] = None
    request_health: Optional[RequestHealth] = None
    request_volume: Optional[Graph] = None
    throughput: ThroughputData
    degraded: bool = False
    generated_at: str
    refresh_interval_seconds: int = 60
    data_state: str = "ok"  # "ok" | "empty_window" | "empty_all_time"
    is_stale: bool = False


class TenantConsumptionResponse(BaseModel):
    scope: Scope
    tenant_ranking: list[TenantRow]
    usage_by_service: list[TenantServiceRow]
    throughput: Optional[ThroughputData] = None      # Throughput & Load: avg/peak RPS
    request_volume: Optional[Graph] = None           # Throughput & Load: RPS over time
    degraded: bool = False
    generated_at: str
    refresh_interval_seconds: int = 60
    data_state: str = "ok"  # "ok" | "empty_window" | "empty_all_time"
    is_stale: bool = False


class ServiceConsumptionResponse(BaseModel):
    scope: Scope
    summary: Optional[ServiceSummary] = None
    service_breakdown: list[ServiceRow]
    throughput: ThroughputData
    request_volume: Optional[Graph] = None
    degraded: bool = False
    generated_at: str
    refresh_interval_seconds: int = 60
    data_state: str = "ok"  # "ok" | "empty_window" | "empty_all_time"
    is_stale: bool = False
