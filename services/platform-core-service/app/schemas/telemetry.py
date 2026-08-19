"""Telemetry schemas for request/response validation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TraceSpanContext(BaseModel):
    """Span context information."""
    trace_id: str
    span_id: str
    trace_state: str = ""


class TraceSpanAttributes(BaseModel):
    """Flexible span attributes."""
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
    service: str
    tenant_id: Optional[str] = None
    service_version: Optional[str] = None
    environment: Optional[str] = None
    hostname: Optional[str] = None
    spans: List[Dict[str, Any]] = []


class SearchTraceItem(BaseModel):
    """Single trace item in search results."""
    trace_id: str
    service: Optional[str] = None
    task_type: Optional[str] = None
    status: str
    url: Optional[str] = None
    tenant_id: Optional[str] = None
    timestamp: Optional[str] = None


class SearchTraceAggregations(BaseModel):
    """Aggregation stats for search results."""
    total: int
    by_level: Optional[Dict[str, int]] = None
    by_task: Optional[Dict[str, int]] = None
    # True when the matching set exceeded the server's breakdown cap
    # (_MAX_BREAKDOWN_TRACE_IDS) - by_level/by_task then cover only a subset
    # of `total` and should be treated as partial rather than exact.
    partial: bool = False


class SearchTracesResponse(BaseModel):
    """Paginated search traces response."""
    data: List[SearchTraceItem]
    total: int
    page: int
    pageSize: int
    aggregations: SearchTraceAggregations
