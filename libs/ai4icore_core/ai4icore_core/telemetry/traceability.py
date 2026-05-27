"""OpenTelemetry-based trace manager with console export for distributed tracing."""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from .registry import get_attribute_value
from ai4icore_core.context import get_trace_id, set_trace_id

logger = logging.getLogger(__name__)


def _serialize_span_dict(span) -> Dict[str, Any]:
    """Serialize span to dictionary without status field. Reusable across all exporters."""
    from datetime import datetime, timezone

    def _to_iso_string(timestamp_nanos: int) -> str:
        """Convert nanosecond timestamp to ISO 8601 string."""
        if timestamp_nanos is None:
            return None
        seconds = timestamp_nanos // 1_000_000_000
        nanos = timestamp_nanos % 1_000_000_000
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        return dt.replace(microsecond=nanos // 1_000).isoformat()

    result = {
        "name": span.name,
        "context": {
            "trace_id": f"0x{format(span.context.trace_id, '032x')}",
            "span_id": f"0x{format(span.context.span_id, '016x')}",
            "trace_state": str(span.context.trace_state),
        },
        "kind": str(span.kind),
        "parent_id": f"0x{format(span.parent.span_id, '016x')}" if span.parent else None,
        "start_time": _to_iso_string(span.start_time),
        "end_time": _to_iso_string(span.end_time),
        "attributes": dict(span.attributes) if span.attributes else {},
    }

    if span.events:
        result["events"] = [{"name": e.name, "timestamp": _to_iso_string(e.timestamp)} for e in span.events]

    return result


class ConsoleSpanExporter(SpanExporter):
    """Exports spans to console (stdout)."""

    def export(self, spans) -> SpanExportResult:
        for span in spans:
            span_dict = _serialize_span_dict(span)
            print(json.dumps(span_dict))
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        _ = timeout_millis
        return True


def _get_default_mapper_path() -> Path:
    """Resolve default mapper path to libs/ai4icore_core/ai4icore_core/telemetry/util."""
    current = Path.cwd()

    while current != current.parent:
        lib_telemetry = current / "libs" / "ai4icore_core" / "ai4icore_core" / "telemetry" / "util"
        if lib_telemetry.exists():
            logger.info(f"[MAPPER PATH] Found at: {lib_telemetry}")
            return lib_telemetry
        current = current.parent

    fallback = Path("libs/ai4icore_core/ai4icore_core/telemetry/util")
    logger.warning(f"[MAPPER PATH] Not found in search, using fallback: {fallback}")
    return fallback


def _initialize_tracer_provider() -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider with console JSON exporter."""
    resource = Resource.create({
        SERVICE_NAME: "ai4icore-telemetry",
        "environment": "development",
    })

    tracer_provider = TracerProvider(resource=resource)
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    trace.set_tracer_provider(tracer_provider)
    return tracer_provider


_initialize_tracer_provider()

# Global root span to keep trace context alive across stages
_root_span: Optional[trace.Span] = None
_root_span_context_token: Optional[object] = None


class OTelSpan:
    """Wrapper around OpenTelemetry Span with service/stage metadata and trace ID."""

    def __init__(self, otel_span: trace.Span, service: str, stage: str):
        """Initialize OTelSpan wrapper."""
        self.span = otel_span
        self.service = service
        self.stage = stage
        self.attributes: Dict[str, Any] = {}
        self.trace_id = get_trace_id()
        logger.info(f"[TRACE START] trace_id={self.trace_id} {service}/{stage}")

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach attribute to span."""
        self.attributes[key] = value
        self.span.set_attribute(key, value)
        logger.info(f"[SET ATTR] {self.service}/{self.stage} {key}={value} (type={type(value).__name__})")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span.get_span_context().span_id,
            "service": self.service,
            "stage": self.stage,
            "attributes": self.attributes,
        }


class TraceManager:
    """Manages distributed tracing by creating spans and computing attributes from JSON mappers."""

    def __init__(self, base_mapper_path: Optional[str] = None):
        """Initialize TraceManager. Auto-resolves inference-service telemetry path if not provided."""
        if base_mapper_path:
            self.base_mapper_path = Path(base_mapper_path)
        else:
            self.base_mapper_path = _get_default_mapper_path()
        self.service_configs: Dict[str, Dict] = {}
        self.tracer = trace.get_tracer(__name__)
        # Track the first span per request context to reuse for all subsequent spans
        # Key is id(context) - Python's id() of the context object to uniquely identify each request
        self._first_span_per_request: Dict[int, Dict[str, Any]] = {}

    def load_mapper(self, service: str, stage: str) -> Dict[str, list]:
        """Load attribute mapper from <service>/stages.json (cached)."""
        if service not in self.service_configs:
            mapper_path = self.base_mapper_path / service / "stages.json"
            logger.info(f"[MAPPER LOAD] service={service}, path={mapper_path}")

            if not mapper_path.exists():
                logger.error(f"[MAPPER MISSING] Not found at: {mapper_path}")
                self.service_configs[service] = {}
            else:
                logger.info(f"[MAPPER FOUND] Loaded from: {mapper_path}")
                try:
                    with open(mapper_path, "r") as f:
                        config = json.load(f)
                        logger.info(f"[MAPPER JSON] {service} has {len(config)} stages")
                        self.service_configs[service] = config
                except Exception as e:
                    logger.error(f"[MAPPER ERROR] Failed to load {mapper_path}: {e}")
                    self.service_configs[service] = {}

        stages = self.service_configs.get(service, {})
        stage_config = stages.get(stage, {"start": [], "end": []})
        logger.debug(f"[MAPPER STAGE] {service}/{stage}: start={len(stage_config.get('start', []))} attrs, end={len(stage_config.get('end', []))} attrs")
        return stage_config

    def trace_stage_start(
        self,
        service: str,
        stage: str,
        request: Dict[str, Any]
    ) -> OTelSpan:
        """Create span and attach START attributes computed from request.

        Synchronizes OTel trace_id back to context to ensure logs and spans
        use the same trace_id for the entire request.
        All spans in the request are children of the first span.
        """
        current_trace_id = get_trace_id()
        span_name = stage

        # Use the current async context's identity as the key
        # This uniquely identifies each request/task
        from contextvars import copy_context
        ctx = copy_context()
        ctx_id = id(ctx)

        # Check if this request context already has a synced first span
        if ctx_id in self._first_span_per_request:
            # Use the existing root span for child spans
            span_info = self._first_span_per_request[ctx_id]
            root_span = span_info["root_span"]
            otel_trace_id = span_info["otel_trace_id"]

            # Create child span within the root span's context
            with trace.use_span(root_span):
                otel_span = self.tracer.start_span(span_name)

            # Ensure this span also uses the synced trace_id
            set_trace_id(otel_trace_id)
        else:
            # First span in this request - create it and extract OTel's generated trace_id
            root_otel_span = self.tracer.start_span(span_name)
            span_context = root_otel_span.get_span_context()

            # Convert OTel's integer trace_id back to hex string (32 chars)
            otel_trace_id = format(span_context.trace_id, '032x')

            # Store the root span for subsequent spans in this request
            self._first_span_per_request[ctx_id] = {
                "root_span": root_otel_span,
                "otel_trace_id": otel_trace_id,
                "original_trace_id": current_trace_id
            }

            # Sync the OTel trace_id back to the application context
            # This ensures all subsequent logs use the same trace_id as the spans
            if otel_trace_id != current_trace_id:
                set_trace_id(otel_trace_id)

            otel_span = root_otel_span

        span = OTelSpan(otel_span, service, stage)
        mapper = self.load_mapper(service, stage)
        start_attrs = mapper.get("start", [])
        logger.info(f"[TRACE START] {service}/{stage} - Found {len(start_attrs)} start attributes to compute")
        logger.debug(f"[TRACE START] mapper={mapper}, request_type={type(request).__name__}")

        for i, config in enumerate(start_attrs):
            attr_name = config.get("attr", f"attr_{i}")
            logger.info(f"[ATTR {i}] Computing {attr_name} from {service}/{stage}")
            value = get_attribute_value(config, request)
            if value is not None:
                logger.info(f"[ATTR {i}] SUCCESS: {attr_name}={value}")
                span.set_attribute(config.get("attr"), value)
            else:
                logger.warning(f"[ATTR {i}] SKIPPED: {attr_name} returned None")
        return span

    def trace_stage_end(self, span: OTelSpan, response: Dict[str, Any]) -> None:
        """Attach END attributes and close span (triggers console export)."""
        mapper = self.load_mapper(span.service, span.stage)
        end_attrs = mapper.get("end", [])
        logger.info(f"[TRACE END] {span.service}/{span.stage} - Found {len(end_attrs)} end attributes to compute")
        logger.debug(f"[TRACE END] mapper={mapper}, response_type={type(response).__name__}")

        for i, config in enumerate(end_attrs):
            attr_name = config.get("attr", f"attr_{i}")
            logger.info(f"[ATTR END {i}] Computing {attr_name} from {span.service}/{span.stage}")
            value = get_attribute_value(config, response)
            if value is not None:
                logger.info(f"[ATTR END {i}] SUCCESS: {attr_name}={value}")
                span.set_attribute(config.get("attr"), value)
            else:
                logger.warning(f"[ATTR END {i}] SKIPPED: {attr_name} returned None")

        span.span.end()
        logger.info(f"[TRACE RESULT] {json.dumps(span.to_dict(), indent=2)}")

    def finalize_trace(self, trace_id: Optional[str] = None) -> None:
        """Clean up the context tracking for a trace.

        Call this when a request/trace is fully processed to clean up
        internal tracking and allow garbage collection.
        """
        from contextvars import copy_context
        ctx = copy_context()
        ctx_id = id(ctx)

        # Clean up the context-based tracking
        if ctx_id in self._first_span_per_request:
            self._first_span_per_request.pop(ctx_id)
            logger.debug(f"Finalized trace context")


_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get or create the global TraceManager instance."""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager

