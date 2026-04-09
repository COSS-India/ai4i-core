"""
Standard span helpers for AI4ICore services.

Implements the 7-phase lifecycle proposed in "Telemetry Step Standardization":

{svc}.inference (router span exists today; this helper can also create it when needed)
  {svc}.preprocess
  {svc}.resolve_model (optional)
  {svc}.triton_inference
    triton.inference (internal leaf; created by the Triton client)
  {svc}.postprocess
  {svc}.persist

Phase 7: set final metrics on the parent {svc}.inference before it ends.
"""

from __future__ import annotations

import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Span

    _TRACING_AVAILABLE = True
except Exception:  # pragma: no cover
    trace = None  # type: ignore
    Status = None  # type: ignore
    StatusCode = None  # type: ignore
    Span = None  # type: ignore
    _TRACING_AVAILABLE = False


@dataclass(frozen=True)
class _InferenceContext:
    start_time: float


class StandardSpanManager:
    """
    Helper to create consistent, low-noise spans for AI4I services.

    Notes:
    - This is intentionally "thin": it standardizes span names + required attributes.
    - It does NOT change business logic or enforce how services resolve model/client/db, etc.
    - If OpenTelemetry is not available, all context managers become no-ops.
    """

    def __init__(self, service_prefix: str, tracer_name: Optional[str] = None):
        self.service_prefix = service_prefix
        self._tracer_name = tracer_name or f"{service_prefix}-service"
        self._tracer = trace.get_tracer(self._tracer_name) if _TRACING_AVAILABLE else None

    def _svc_key(self, key: str) -> str:
        return f"{self.service_prefix}.{key}"

    def _set_if_not_none(self, span: Any, key: str, value: Any) -> None:
        if span is None:
            return
        if value is None:
            return
        span.set_attribute(key, value)

    def _set_required_inference_attrs(
        self,
        span: Any,
        *,
        service_id: Optional[str] = None,
        model_name: Optional[str] = None,
        input_count: Optional[int] = None,
        input_type: Optional[str] = None,
        output_count: Optional[int] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        extra_attrs: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Required (service-prefixed) attributes on {svc}.inference
        self._set_if_not_none(span, self._svc_key("service_id"), service_id)
        self._set_if_not_none(span, self._svc_key("model_name"), model_name)
        self._set_if_not_none(span, self._svc_key("input_count"), input_count)
        self._set_if_not_none(span, self._svc_key("input_type"), input_type)
        self._set_if_not_none(span, self._svc_key("output_count"), output_count)

        # Required cross-service auth attributes
        self._set_if_not_none(span, "user.id", user_id)
        self._set_if_not_none(span, "api_key.id", api_key_id)
        self._set_if_not_none(span, "session.id", session_id)

        if extra_attrs:
            for k, v in extra_attrs.items():
                self._set_if_not_none(span, k, v)

    def _finalize_inference_span(self, span: Any, ctx: _InferenceContext, status: str) -> None:
        if span is None:
            return
        processing_time_seconds = time.time() - ctx.start_time
        span.set_attribute(self._svc_key("processing_time_seconds"), processing_time_seconds)
        span.set_attribute(self._svc_key("status"), status)

    @contextmanager
    def inference(
        self,
        *,
        service_id: Optional[str] = None,
        model_name: Optional[str] = None,
        input_count: Optional[int] = None,
        input_type: Optional[str] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        extra_attrs: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """
        Create the parent {svc}.inference span (Phase 1) and auto-finalize Phase 7 attributes.

        If your router already creates {svc}.inference, prefer phase spans only and finalize
        attributes on the router span. This method exists for services that want a single helper
        to own the whole lifecycle.
        """
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return

        ctx = _InferenceContext(start_time=time.time())
        with self._tracer.start_as_current_span(self._svc_key("inference")) as span:
            self._set_required_inference_attrs(
                span,
                service_id=service_id,
                model_name=model_name,
                input_count=input_count,
                input_type=input_type,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                extra_attrs=extra_attrs,
            )
            try:
                yield span
                self._finalize_inference_span(span, ctx, "success")
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                self._finalize_inference_span(span, ctx, "error")
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def preprocess(self) -> Iterator[Any]:
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(self._svc_key("preprocess")) as span:
            yield span

    @contextmanager
    def resolve_model(self) -> Iterator[Any]:
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(self._svc_key("resolve_model")) as span:
            yield span

    @contextmanager
    def triton_inference(self) -> Iterator[Any]:
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(self._svc_key("triton_inference")) as span:
            yield span

    @contextmanager
    def postprocess(self) -> Iterator[Any]:
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(self._svc_key("postprocess")) as span:
            yield span

    @contextmanager
    def persist(self) -> Iterator[Any]:
        if not self._tracer:
            with nullcontext() as span:
                yield span
            return
        with self._tracer.start_as_current_span(self._svc_key("persist")) as span:
            yield span
