"""Telemetry schemas for request/response validation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TraceSpanContext(BaseModel):
    """Span context information."""
    trace_id: str
    span_id: str
    trace_state: str = ""


class TraceSpanAttributes(BaseModel):
    """Flexible span attributes — mirrors what the inference service emits per span."""
    total_time_ms: Optional[float] = None
    url: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    status_code: Optional[int] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    task_type: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    input_type: Optional[str] = None
    output_type: Optional[str] = None

    class Config:
        extra = "allow"
        protected_namespaces = ()


# Column keys that differ from their TraceSpanAttributes field name.
_COLUMN_KEY_ALIASES: Dict[str, str] = {
    "model":   "model_name",
    "latency": "total_time_ms",
}

# Columns sourced from span metadata, status description, or context attributes
# — present on every span, not specific to a single span type.
_NON_ATTR_COLUMNS: frozenset = frozenset({
    "timestamp", "institution", "service", "error", "application", "end_user", "metadata",
})

# Derived from TraceSpanAttributes fields: swap aliased field names for their
# column key equivalents, then add the non-attribute columns.
VALID_COLUMN_KEYS: frozenset = (
    (frozenset(TraceSpanAttributes.model_fields) - frozenset(_COLUMN_KEY_ALIASES.values()))
    | frozenset(_COLUMN_KEY_ALIASES.keys())
    | _NON_ATTR_COLUMNS
)
DEFAULT_COLUMN_KEYS: frozenset = frozenset({"timestamp", "status", "task_type", "url", "institution"})


class TraceSpan(BaseModel):
    """Represents a single span in a trace."""
    name: str
    context: TraceSpanContext
    kind: str
    attributes: Dict[str, Any]
    timestamp: str
    logger: Optional[str] = None
    taskName: Optional[str] = None


class TraceResponse(BaseModel):
    """Complete trace response with all spans."""
    trace_id: str
    service: Optional[str] = None
    tenant_id: Optional[str] = None
    service_version: Optional[str] = None
    environment: Optional[str] = None
    hostname: Optional[str] = None
    spans: List[Dict[str, Any]] = []


class SearchTraceAggregations(BaseModel):
    """Aggregation stats for search results."""
    total: int
    by_level: Optional[Dict[str, int]] = None
    by_task: Optional[Dict[str, int]] = None
    # True when the matching set exceeded the server's breakdown cap
    # (_MAX_BREAKDOWN_TRACE_IDS) - by_level/by_task then cover only a subset
    # of `total` and should be treated as partial rather than exact.
    partial: bool = False


class SearchTraceSummary(BaseModel):
    """Success/failure counts for the full matching result set."""
    success: int = 0
    failure: int = 0


class SearchTracesResponse(BaseModel):
    """Paginated search traces response."""
    data: List[Dict[str, Any]]  # fields vary per selected columns
    total: int
    page: int
    pageSize: int
    aggregations: SearchTraceAggregations
    summary: SearchTraceSummary = Field(default_factory=SearchTraceSummary)
