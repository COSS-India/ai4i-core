"""
Standard span helpers for AI4ICore services.

Implements the 7-phase lifecycle proposed in "Telemetry Step Standardization":

{svc}.inference (router span exists today; this helper can also create it when needed)
  {svc}.preprocess
  {svc}.resolve_model (optional)
  {svc}.triton_inference
    triton.inference (internal leaf; created by the Triton client)
  {svc}.postprocess
  {svc}.persist  (or {svc}.persist_<suffix> e.g. persist_request / persist_results when DB is split)

Phase 7: set final metrics on the parent {svc}.inference before it ends.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
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


class _NoOpSpan:
    """
    Minimal no-op span used when OpenTelemetry is unavailable.

    IMPORTANT: If service code starts calling additional span APIs (e.g. end(), update_name(),
    get_span_context(), etc.) while tracing may be disabled, add matching no-op methods here
    to avoid AttributeError in those environments.
    """
    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add_event(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        return None

    def is_recording(self) -> bool:
        return False


_NOOP_SPAN = _NoOpSpan()


@contextmanager
def _noop_span_context() -> Iterator[_NoOpSpan]:
    yield _NOOP_SPAN


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
    - Repo migration status (gradual rollout):
      - Migrated to StandardSpanManager phases: nmt-service, asr-service, tts-service,
        transliteration-service, ocr-service, audio-lang-detection-service,
        speaker-diarization-service, language-diarization-service,
        language-detection-service, ner-service.
      - Not yet migrated (still primarily uses raw tracer spans): (others as applicable).
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
            with _noop_span_context() as span:
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
            with _noop_span_context() as span:
                yield span
                return
        with self._tracer.start_as_current_span(self._svc_key("preprocess")) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def resolve_model(self) -> Iterator[Any]:
        if not self._tracer:
            with _noop_span_context() as span:
                yield span
                return
        with self._tracer.start_as_current_span(self._svc_key("resolve_model")) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def triton_inference(self) -> Iterator[Any]:
        if not self._tracer:
            with _noop_span_context() as span:
                yield span
                return
        with self._tracer.start_as_current_span(self._svc_key("triton_inference")) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def postprocess(self) -> Iterator[Any]:
        if not self._tracer:
            with _noop_span_context() as span:
                yield span
                return
        with self._tracer.start_as_current_span(self._svc_key("postprocess")) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    @contextmanager
    def persist(self, *, suffix: Optional[str] = None) -> Iterator[Any]:
        """
        Phase 6 span. Default name is {svc}.persist.

        Use suffix when one logical persist phase is split (e.g. create_request vs store_results):
        suffix=\"request\" -> {svc}.persist_request, suffix=\"results\" -> {svc}.persist_results.
        """
        phase = f"persist_{suffix}" if suffix else "persist"
        if not self._tracer:
            with _noop_span_context() as span:
                yield span
                return
        with self._tracer.start_as_current_span(self._svc_key(phase)) as span:
            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
