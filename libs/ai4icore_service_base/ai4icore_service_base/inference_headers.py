"""
Middleware that adds X-Trace-Id and X-Inference-Model-Time response headers.

X-Trace-Id: OpenTelemetry trace ID (128-bit hex) for Jaeger/distributed tracing.
    Falls back to correlation ID if OTel is not available.
X-Inference-Model-Time: Cumulative Triton inference time in milliseconds.
    Only present when at least one Triton call was made.

Flow:
1. Middleware stores ASGI scope ref in a ContextVar (_current_scope)
2. TritonClient reads scope from ContextVar and writes timing into scope dict
3. Middleware reads timing from scope dict when building response headers
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ai4icore_model_management.triton_client import _current_scope, SCOPE_KEY

# Optional OpenTelemetry for real trace ID
try:
    from opentelemetry import trace as otel_trace

    _OTEL = True
except ImportError:
    _OTEL = False


def _get_otel_trace_id() -> str:
    """Get the current OpenTelemetry trace ID as 32-char hex string."""
    if not _OTEL:
        return ""
    span = otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""


class InferenceHeadersMiddleware:
    """Add trace ID and inference model timing to response headers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Initialize timing in scope and make scope accessible to TritonClient
        scope[SCOPE_KEY] = 0.0
        token = _current_scope.set(scope)

        # Buffer http.response.start so we can inject headers after route completes
        initial_message = None

        async def send_wrapper(message: Message) -> None:
            nonlocal initial_message

            if message["type"] == "http.response.start":
                initial_message = message
                return

            if message["type"] == "http.response.body" and initial_message is not None:
                headers = list(initial_message.get("headers", []))

                # X-Trace-Id — prefer OTel trace ID, fall back to correlation ID
                otel_tid = _get_otel_trace_id()
                if otel_tid:
                    headers.append((b"x-trace-id", otel_tid.encode()))
                else:
                    request = Request(scope)
                    fallback = getattr(request.state, "trace_id", None) or getattr(
                        request.state, "correlation_id", None
                    )
                    if fallback:
                        headers.append((b"x-trace-id", str(fallback).encode()))

                # X-Inference-Model-Time
                model_time = scope.get(SCOPE_KEY, 0.0)
                if model_time > 0:
                    headers.append(
                        (b"x-inference-model-time", f"{model_time:.1f}ms".encode())
                    )

                initial_message["headers"] = headers
                await send(initial_message)
                initial_message = None

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _current_scope.reset(token)
