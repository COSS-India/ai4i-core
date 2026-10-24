"""Telemetry schemas for request/response validation."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ColumnDefinition(BaseModel):
    """User-facing metadata for one column in the trace search column picker."""
    key: str
    label: str
    default: bool
    filterable: bool
    sortable: bool
    keyword_searchable: bool


# Static column definitions — single source of truth for the column picker.
# os_field/span are internal routing hints used by the search endpoint to
# determine which OpenSearch fields to read and which span types to fetch.
# The /traces/columns endpoint exposes only the user-facing fields via ColumnDefinition.
COLUMN_DEFINITIONS: List[Dict[str, Any]] = [
    {"key": "timestamp",   "label": "Timestamp",   "default": True,  "filterable": False, "sortable": True,  "keyword_searchable": False, "os_field": "@timestamp",               "span": None},
    {"key": "status",      "label": "Status",      "default": True,  "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "attributes.status",        "span": None},
    {"key": "task_type",   "label": "Task Type",   "default": True,  "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "attributes.task_type",     "span": "model"},
    {"key": "url",         "label": "URL",         "default": True,  "filterable": False, "sortable": True,  "keyword_searchable": True,  "os_field": "attributes.url",           "span": "request"},
    {"key": "institution", "label": "Institution", "default": True,  "filterable": True,  "sortable": False, "keyword_searchable": False, "os_field": "attributes.tenantId",      "span": None},
    {"key": "status_code", "label": "Status Code", "default": False, "filterable": True,  "sortable": True,  "keyword_searchable": True,  "os_field": "attributes.status_code",   "span": "request"},
    {"key": "error",       "label": "Error",       "default": False, "filterable": False, "sortable": False, "keyword_searchable": True,  "os_field": "attributes.error",         "span": "request"},
    {"key": "service",     "label": "Service",     "default": False, "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "service_name",             "span": None},
    {"key": "model",       "label": "Model",       "default": False, "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "attributes.model_name",    "span": "model"},
    {"key": "latency",     "label": "Latency (ms)","default": False, "filterable": False, "sortable": True,  "keyword_searchable": False, "os_field": "attributes.total_time_ms", "span": "request"},
    {"key": "application", "label": "Application", "default": False, "filterable": False, "sortable": False, "keyword_searchable": True,  "os_field": "attributes.app_id",        "span": None},
    {"key": "api_key",     "label": "API Key",     "default": False, "filterable": False, "sortable": False, "keyword_searchable": True,  "os_field": "attributes.api_key_id",    "span": None},
    {"key": "end_user",    "label": "End User",    "default": False, "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "attributes.enduser.id",    "span": None},
    {"key": "metadata",    "label": "Metadata",    "default": False, "filterable": True,  "sortable": False, "keyword_searchable": True,  "os_field": "attributes.metadata_kv",  "span": None},
    {"key": "method",      "label": "Method",      "default": False, "filterable": False, "sortable": False, "keyword_searchable": False, "os_field": "attributes.method",        "span": "request"},
]

VALID_COLUMN_KEYS: frozenset = frozenset(col["key"] for col in COLUMN_DEFINITIONS)
DEFAULT_COLUMN_KEYS: frozenset = frozenset(col["key"] for col in COLUMN_DEFINITIONS if col["default"])
COLUMN_SPAN_DEP: Dict[str, Optional[str]] = {col["key"]: col["span"] for col in COLUMN_DEFINITIONS}
ALL_SPAN_TYPES: frozenset = frozenset({"request", "model", "ai-inference"})


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
