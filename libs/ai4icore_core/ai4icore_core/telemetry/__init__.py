"""
AI4ICore Telemetry Library

OpenTelemetry-based distributed tracing with console export.

Core Features:
  - OpenTelemetry SDK for Python: Standard distributed tracing
  - Console exporter: Traces logged as JSON to stdout
  - Mapper-based attributes: JSON-configurable span attributes
  - Decorator support: @trace_stage for automatic span management
  - Context propagation: W3C Trace Context support

Quick Start:
    from ai4icore_core.telemetry import get_trace_manager, trace_stage, async_trace_stage

    # Option 1: Manual span management
    manager = get_trace_manager()
    span = manager.trace_stage_start("ocr", "preprocess", request)
    try:
        result = process(request)
        manager.trace_stage_end(span, result)
    except Exception:
        span.span.end()
        raise

    # Option 2: Decorator-based (sync)
    @trace_stage("inference")
    def run_inference(self, request):
        return self.model.predict(request)

    # Option 3: Decorator-based (async, recommended for async services)
    @async_trace_stage("triton_inference")
    async def run_inference(self, request):
        return await self.model.predict(request)
"""

from .traceability import TraceManager, OTelSpan, get_trace_manager
from .trace_wrapper import trace_stage, async_trace_stage, TraceableService
from .registry import get_attribute_value
from .trace_middleware import TraceIDMiddleware
from .propagator import (
    extract_trace_context,
    inject_trace_context,
    initialize_trace_context,
    get_current_trace_id,
)

__all__ = [
    "TraceIDMiddleware",
    "TraceManager",
    "OTelSpan",
    "get_trace_manager",
    "trace_stage",
    "async_trace_stage",
    "TraceableService",
    "get_attribute_value",
    "extract_trace_context",
    "inject_trace_context",
    "initialize_trace_context",
    "get_current_trace_id",
]

__version__ = "2.0.0"