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


class ServiceModelRow(BaseModel):
    service_id: str                     # raw value the client sent in the OpenAI `model` field; the grouping key
    name: str                           # mm_services.name, falls back to service_id when unresolved
    model_id: Optional[str] = None      # mm_models.model_id — stable (name, version) hash; the model-level grouping key (FE: group rows by this, not model_name)
    model_name: Optional[str] = None    # mm_models.name — the actual model behind the service; display only, not an identity
    task_type: Optional[str] = None     # mm_models.task["type"] (Registry's TaskTypeEnum value, e.g. "nmt", "audio-lang-detection") — None when the model/task type couldn't be resolved
    requests: int
    native_units: float = 0.0
    native_unit_suffix: Optional[str] = None  # e.g. "chars", "min", "tokens" — task-specific; None alongside an unresolved task_type
    success_pct: float
    failure_rate_pct: float = 0.0   # 100 - success_pct


class MostUsedModel(BaseModel):
    """Model-level (not service-level) — ``requests`` is the sum across every
    service backed by this model. ``service_id`` is omitted (None) since a
    model can be fronted by more than one service."""
    service_id: Optional[str] = None
    model_id: Optional[str] = None
    name: Optional[str] = None
    requests: int = 0


class HighestFailureModel(BaseModel):
    service_id: Optional[str] = None
    name: Optional[str] = None
    failure_rate_pct: float = 0.0


class TopModelRow(BaseModel):
    """One row of the model-level consumption ranking (AI4IDS-2790).

    ``consumption_pct`` is this model's share of total requests in the
    window; when more than one service backs the model, it's the AVERAGE of
    those services' individual consumption % (per AC), not the sum.
    ``requests`` is the SUM of requests across the model's service(s).
    """
    rank: int
    model_id: str
    model_name: str
    consumption_pct: float
    requests: int
    formatted_requests: str


class ModelConsumptionSummary(BaseModel):
    """Model Consumption KPI cards (computed over services with traffic)."""
    total_models: Optional[int] = None      # count of registered LLM model VERSIONS (mm_models, task_types=llm); see note in metering_service.registry_model_count
    active_models: Optional[int] = None     # distinct model_ids among model_totals with traffic in the window — matches top_models' own grain
    overall_success_rate_pct: Optional[float] = None  # plain average of success_pct across services with traffic — unweighted by request volume
    most_used: Optional[MostUsedModel] = None
    highest_failure_rate: Optional[HighestFailureModel] = None


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


class ModelConsumptionResponse(BaseModel):
    scope: Scope
    summary: Optional[ModelConsumptionSummary] = None
    top_models: list[TopModelRow] = []   # ranked by consumption_pct desc; FE slices to Top 5 / Top 10
    # Denominator for top_models[].consumption_pct — sum of requests across
    # services with a RESOLVED model_name only. NOT the full window's total
    # requests (that also includes traffic from services whose model lookup
    # failed) — render this alongside consumption_pct, not some other total,
    # or the percentages won't add up against what's displayed next to them.
    top_models_total_requests: int = 0
    breakdown: list[ServiceModelRow]
    degraded: bool = False
    generated_at: str
