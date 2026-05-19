"""
CorrelationPropagator — bridges the correlation trace ID into OTel.

RequestMiddleware (logging layer) runs before OTel middleware and seeds
ai4icore_core.context with a 32-hex trace ID.  When OTel's middleware calls
propagator.extract(), this propagator reads that trace ID and injects it as
the OTel SpanContext so Jaeger uses the same ID as the logs.

Priority rules:
- If a valid W3C traceparent context already exists (upstream service sent one),
  that trace is respected and this propagator is a no-op.
- Otherwise, the correlation trace ID from context becomes the OTel trace ID.
"""

import secrets
from typing import Optional

try:
    from opentelemetry import trace
    from opentelemetry.context import Context
    from opentelemetry.propagators.textmap import TextMapPropagator, Getter, Setter, default_getter
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from ai4icore_core.context import get_trace_id


if OTEL_AVAILABLE:
    class CorrelationPropagator(TextMapPropagator):
        """
        Injects the correlation trace ID (from ai4icore_core.context) into the
        OTel context as the root SpanContext, so OTel spans share the same
        trace ID as structured logs.
        """

        def extract(
            self,
            carrier,
            context: Optional[Context] = None,
            getter: Getter = default_getter,
        ) -> Context:
            # Don't override if a valid trace context already exists — an upstream
            # service sent a traceparent header and the W3C propagator parsed it.
            existing_span = trace.get_current_span(context)
            if existing_span and existing_span.get_span_context().is_valid:
                return context or Context()

            trace_id_hex = get_trace_id()
            if not trace_id_hex:
                return context or Context()

            try:
                span_ctx = SpanContext(
                    trace_id=int(trace_id_hex, 16),
                    span_id=int(secrets.token_hex(8), 16),
                    is_remote=True,
                    trace_flags=TraceFlags(TraceFlags.SAMPLED),
                )
                return trace.set_span_in_context(NonRecordingSpan(span_ctx), context)
            except Exception:
                return context or Context()

        def inject(self, carrier, context: Optional[Context] = None, setter: Setter = None) -> None:
            # Outbound propagation is handled by the W3C propagator (traceparent header).
            pass

        @property
        def fields(self):
            return set()

else:
    class CorrelationPropagator:  # type: ignore[no-redef]
        """No-op when OpenTelemetry is not installed."""

        def extract(self, carrier, context=None, getter=None):
            return context

        def inject(self, carrier, context=None, setter=None):
            pass

        @property
        def fields(self):
            return set()
