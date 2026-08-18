"""
Middleware for AI4ICore Observability Plugin.

Handles request tracking, path-based service detection, and Prometheus metric
emission. Tenant is read from the gateway-injected ``X-Tenant-Name`` header
(the tenant's organisation name, set by ``auth-service /validate`` from its
in-memory tenant_name_cache) — this middleware does NOT decode JWTs, does NOT
look up the tenant id itself, and does NOT open OpenTelemetry spans.

ROLLOUT NOTE: the ``tenant`` label value changed from the numeric tenant id to
the organisation name here. Series written before a deploy of this change
keep the old id value forever — Prometheus has no way to rewrite a stored
series' label after the fact — so any dashboard query window spanning the
cutover moment mixes two label values for what was really one tenant (see
MeteringService.active_tenants for the concrete symptom). This clears itself
once pre-cutover series age out of the query window; no relabel rule can fix
it retroactively since relabeling only sees a scrape target's own labels, not
a historical series' stored value.

Unit counts (characters/audio-minutes/images/tokens), language labels, and
service_id are NOT re-derived here — this middleware never reads or parses
the request body at all. Every value is computed exactly once by the request
handler (task_service.py / llm_service.py, via trace/span_attributes.py) —
the same values already used to bill the request and attached to the
ai-inference OTel span. Orchestrator.route_inference (Triton) and the LLM
chat route mirror them onto ``request.state``: ``billed_input`` /
``billed_output`` are the billed quantities (via ``set_billed_state``);
``source_lang`` / ``target_lang`` / ``model`` / ``model_id`` / ``service_id``
are metric labels, not billing data (languages + model + model_id via
``set_metric_labels``, service_id set at resolution time). This middleware only reads them, so
Prometheus can never disagree with what was actually billed, and the request
body is never parsed a second time. OCR bills and is tracked purely by image
count (``billed_input`` via ``track_ocr_characters``) — there is no separate
size-based metric.
"""
import asyncio
import logging
import time
from typing import Any, AsyncIterator, Optional, Union
from urllib.parse import unquote

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import PluginConfig
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


def _tenant_label(request: Request) -> str:
    """Read the ``tenant`` metric label from the gateway-injected
    X-Tenant-Name header (organisation name, set by auth-service /validate).

    auth-service percent-encodes the name when it isn't latin-1 encodable
    (Starlette can only send latin-1 header values) — undo that here so the
    label carries the real Unicode organisation name, not the encoded form.
    """
    return unquote((request.headers.get("X-Tenant-Name") or "").strip()) or "unknown"


def set_billed_state(
    request: Request,
    *,
    billed_input: float,
    billed_output: float = 0,
) -> None:
    """Record the billed quantities on ``request.state`` for
    ObservabilityMiddleware to read, so it never re-parses the request body.

    This is the WRITE side of the request.state contract the middleware reads
    (see this module's docstring). Every inference handler must call it once,
    after the billed count is known, instead of setting the ``billed_*``
    attributes by hand — that keeps the attribute names in one place so a new
    inference path can't silently diverge from what the middleware looks for.
    ``billed_input`` / ``billed_output`` are the same counts on the
    ai-inference span (billing's source of truth) — the ``billed_`` prefix
    marks them as the quantities that actually get billed, so the metric
    equals the bill.

    Metric LABELS (``source_lang`` / ``target_lang`` / ``model``) are not
    billing data and are NOT set here — set them with ``set_metric_labels``.
    ``service_id`` is likewise separate: handlers set it right after service
    resolution (before inference runs) so it survives an inference failure,
    whereas the billed count only exists on success.
    """
    st = request.state
    st.billed_input = billed_input
    st.billed_output = billed_output


class _Unset:
    """Sentinel type distinguishing "caller omitted this argument" from any
    real value a caller might pass (including an explicit ""). Its own type
    — rather than a bare ``object()`` typed as ``str`` — lets the parameter
    annotations below say what's actually accepted: a ``str``, or this
    sentinel."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<UNSET>"


_UNSET = _Unset()


def set_metric_labels(
    request: Request,
    *,
    source_lang: Union[str, _Unset] = _UNSET,
    target_lang: Union[str, _Unset] = _UNSET,
    model: Union[str, _Unset] = _UNSET,
    model_id: Union[str, _Unset] = _UNSET,
) -> None:
    """Record Prometheus metric LABELS on ``request.state`` (not billing data).

    ``source_lang`` / ``target_lang`` drive the per-language dashboard
    breakdown for NMT/TTS/ASR/transliteration; ``model`` is the ``model``
    label on the LLM token metric; ``model_id`` is the Model Registry's
    stable identifier for the model behind the service (distinct from
    ``model`` — see MetricsCollector._init_metrics), set on
    ``telemetry_obsv_requests_total``/``_duration_seconds``/
    ``_llm_tokens_processed``. None of these are billed quantities — they're
    dimensions on the metrics. They ride request.state only so the
    middleware doesn't re-read the body to label its metrics.

    A field the caller doesn't pass is left as-is if already set, or
    defaulted to "" on first write — it is NOT reset to "". This matters
    because ``model_id`` is typically known (and set) as soon as the service
    resolves, BEFORE a handler runs, while ``source_lang``/``target_lang``
    are usually only known AFTER it runs — so a caller commonly calls this
    twice per request (once early with just ``model_id``, once later with
    the rest). Overwriting-to-"" on every call would let the second,
    partial call silently erase the first call's ``model_id`` — losing it
    specifically on any request that fails/raises between the two calls
    (e.g. an upstream 502), which is exactly when a caller most needs the
    label preserved. See orchestrator.route_inference for the concrete
    two-call pattern.
    """
    st = request.state
    if source_lang is not _UNSET:
        st.source_lang = source_lang
    elif not hasattr(st, "source_lang"):
        st.source_lang = ""
    if target_lang is not _UNSET:
        st.target_lang = target_lang
    elif not hasattr(st, "target_lang"):
        st.target_lang = ""
    if model is not _UNSET:
        st.model = model
    elif not hasattr(st, "model"):
        st.model = ""
    if model_id is not _UNSET:
        st.model_id = model_id
    elif not hasattr(st, "model_id"):
        st.model_id = ""


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking requests and collecting metrics."""

    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None,
                 config: Optional[PluginConfig] = None):
        super().__init__(app)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.config = config or PluginConfig()
        # asyncio.create_task only keeps a weak reference; hold strong refs
        # here so background metric tasks aren't GC'd before they finish.
        self._pending_tasks: "set[asyncio.Task[Any]]" = set()

    async def dispatch(self, request: Request, call_next):
        if not self.config.enabled:
            return await call_next(request)

        start_time = time.time()
        path = request.url.path
        method = request.method
        service_type = self._detect_service_type(path)

        if self.config.debug:
            logger.debug(f"Request: {method} {path} -> service_type={service_type}")

        # Run the actual handler. All observability work happens AFTER the
        # response is in hand so we never block the user. No response-body
        # buffering needed anymore — billed_* already carries what we'd have
        # re-parsed the response for.
        response = await call_next(request)

        # LLM (chat / chat-completions): for a streaming (SSE) response the
        # billed token counts only land on request.state AFTER the app's own
        # generator finishes (the final SSE chunk carries the usage block), so
        # reading state here would be too early. Defer metric emission until
        # the body is fully drained by wrapping the response iterator — chunks
        # are forwarded untouched, so the stream stays live (never buffered).
        # The same wrapper is correct for the non-stream JSON shape too
        # (single chunk, state already populated), keeping one code path.
        if service_type == "llm":
            response.body_iterator = self._wrap_llm_response(
                response.body_iterator,
                request=request,
                path=path,
                method=method,
                status_code=response.status_code,
                start_time=start_time,
            )
            return response

        duration = time.time() - start_time

        # service_id is populated during request handling by model-management.
        tenant_label = _tenant_label(request)
        # service_id is set on request.state by the route handler for LLM
        # (from payload serviceId before proxy_traced is called) and by the
        # orchestrator for Triton services. Falls back to empty string.
        service_id = getattr(request.state, "service_id", "") or ""

        # The billed count — set by orchestrator.route_inference (Triton) or
        # the LLM chat route, from the same computation used for billing and
        # the OpenSearch trace. None means the handler never set it (e.g. a
        # non-inference path, or an error before billing ran).
        billed_input = getattr(request.state, "billed_input", None)
        billed_output = getattr(request.state, "billed_output", None)
        # Metric labels (not billed quantities) — set alongside the billed
        # count from the same single parse, so a label can never disagree
        # with what a second body parse would have produced.
        source_lang = getattr(request.state, "source_lang", "") or ""
        target_lang = getattr(request.state, "target_lang", "") or ""
        model = getattr(request.state, "model", "") or ""
        model_id = getattr(request.state, "model_id", "") or ""

        # Fire-and-forget: emit metrics WITHOUT blocking the response.
        self._schedule_metrics(
            path=path,
            method=method,
            service_type=service_type,
            tenant=tenant_label,
            service_id=service_id,
            status_code=response.status_code,
            duration=duration,
            billed_input=billed_input,
            billed_output=billed_output,
            source_lang=source_lang,
            target_lang=target_lang,
            model=model,
            model_id=model_id,
        )

        return response

    def _schedule_metrics(self, **kwargs: Any) -> None:
        """Fire-and-forget ``_record_metrics`` WITHOUT blocking the response.

        Holding the task in ``self._pending_tasks`` keeps it alive —
        ``asyncio.create_task`` only keeps a weak reference.
        """
        task = asyncio.create_task(self._record_metrics(**kwargs))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _wrap_llm_response(
        self,
        body_iterator: AsyncIterator[Any],
        *,
        request: Request,
        path: str,
        method: str,
        status_code: int,
        start_time: float,
    ) -> AsyncIterator[Any]:
        """Forward LLM response chunks untouched, then emit metrics once the
        body is fully drained — see the comment in dispatch().

        The route's own generator sets the billed token counts on
        ``request.state`` (via ``set_billed_state``) after its last chunk, and
        Starlette only finishes this iterator after that generator completes,
        so the post-loop reads below always see the final state — for both the
        single-chunk JSON shape and the multi-chunk SSE stream.
        """
        try:
            async for chunk in body_iterator:
                yield chunk
        finally:
            duration = time.time() - start_time
            tenant_label = _tenant_label(request)
            service_id = getattr(request.state, "service_id", "") or ""
            self._schedule_metrics(
                path=path,
                method=method,
                service_type="llm",
                tenant=tenant_label,
                service_id=service_id,
                status_code=status_code,
                duration=duration,
                billed_input=getattr(request.state, "billed_input", None),
                billed_output=getattr(request.state, "billed_output", None),
                model=getattr(request.state, "model", "") or "",
                model_id=getattr(request.state, "model_id", "") or "",
            )

    # ------------------------------------------------------------------
    # Path-based service detection.
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_service_type(path: str) -> str:
        """Detect service type from URL path.

        Pure path-based; never inspects the body. The unified
        ``/api/v1/inference`` endpoint resolves to ``"unknown"`` because the
        task is only knowable from the body — dedicated per-task paths like
        ``/nmt/inference`` resolve to a specific type.
        """
        path_lower = path.lower()
        if any(p in path_lower for p in ("/translation", "/nmt", "/translate")):
            return "translation"
        if any(p in path_lower for p in ("/asr", "/transcribe", "/speech")):
            return "asr"
        if any(p in path_lower for p in ("/tts", "/synthesize")):
            return "tts"
        if any(p in path_lower for p in ("/ocr", "/text-recognition")):
            return "ocr"
        if any(p in path_lower for p in ("/transliteration", "/xlit", "/transliterate")):
            return "transliteration"
        if any(p in path_lower for p in ("/audio-lang-detection", "/audio-language-detection", "/audio-detect")):
            return "audio_lang_detection"
        if any(p in path_lower for p in ("/language-detection", "/lang-detect", "/detect-language")):
            return "language_detection"
        if any(p in path_lower for p in ("/language-diarization", "/language-diarization-compute-call")):
            return "language_diarization"
        if any(p in path_lower for p in ("/speaker-diarization", "/speaker-diarization-compute-call")):
            return "speaker_diarization"
        if any(p in path_lower for p in ("/ner", "/entity", "/entities")):
            return "ner"
        if any(p in path_lower for p in ("/speaker", "/speaker-enrollment", "/speaker-verification", "/speak")):
            return "speaker_verification"
        if any(p in path_lower for p in ("/llm", "/generate", "/chat", "/completion")):
            return "llm"
        if any(p in path_lower for p in ("/enterprise", "/health", "/metrics", "/config")):
            return "enterprise"
        if any(p in path_lower for p in ("/docs", "/openapi", "/redoc")):
            return "documentation"
        return "unknown"

    # ------------------------------------------------------------------
    # Background processing — runs AFTER the response is returned.
    # ------------------------------------------------------------------
    async def _record_metrics(
        self,
        path: str,
        method: str,
        service_type: str,
        tenant: str,
        service_id: str,
        status_code: int,
        duration: float,
        billed_input: Optional[float] = None,
        billed_output: Optional[float] = None,
        source_lang: str = "",
        target_lang: str = "",
        model: str = "",
        model_id: str = "",
    ) -> None:
        """Emit Prometheus metrics out-of-band, using the already-billed count.

        Every value comes from request.state (set once by the route handler /
        orchestrator — see dispatch()); the request body is never read here.
        """
        try:
            # Request count + duration fire for every request, regardless of
            # whether a billed unit was recorded.
            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                tenant=tenant,
                service_id=service_id,
                model_id=model_id,
            )

            # Non-2xx or no billed_* set (e.g. a non-inference path, or the
            # handler zeroed counts on failure — see trace/request_span.py
            # ``_zero_tokens``) — skip rather than emit a misleading 0.
            if status_code >= 400 or billed_input is None:
                return

            if service_type == "llm":
                if billed_input or billed_output:
                    self.metrics_collector.track_llm_tokens(
                        model=model or "unknown",
                        prompt_tokens=billed_input,
                        completion_tokens=billed_output or 0,
                        total_tokens=billed_input + (billed_output or 0),
                        tenant=tenant,
                        service_id=service_id,
                        endpoint=path,
                        model_id=model_id,
                    )
                return

            if billed_input > 0:
                self._track_payload_metrics(
                    service_type=service_type,
                    billed_input=billed_input,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    tenant=tenant,
                    service_id=service_id,
                )

        except Exception:
            if self.config.debug:
                logger.debug("Background metrics recording failed", exc_info=True)

    def _track_payload_metrics(
        self,
        service_type: str,
        billed_input: float,
        source_lang: str,
        target_lang: str,
        tenant: str,
        service_id: str,
    ) -> None:
        """Dispatch billed_input (the single count already used for billing
        and the OpenSearch trace — see trace/span_attributes.py) to the
        matching Prometheus metric for this service_type.

        billed_input's unit depends on service_type's inference_types.yaml
        entry: characters (tts/translation/transliteration/language_detection/
        ner), audio minutes (asr/audio_lang_detection/*_diarization — passed
        straight through, no unit conversion), or images (ocr).
        """
        try:
            if service_type == "tts":
                self.metrics_collector.track_tts_characters(
                    language=source_lang, characters=billed_input,
                    tenant=tenant, service_id=service_id,
                )
            elif service_type == "translation":
                self.metrics_collector.track_nmt_characters(
                    source_lang=source_lang, target_lang=target_lang,
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "asr":
                self.metrics_collector.track_asr_audio_length(
                    language=source_lang, audio_minutes=billed_input,
                    tenant=tenant, service_id=service_id,
                )
            elif service_type == "ocr":
                # billed_input is an image COUNT (inference_types.yaml unit:
                # images), not a character estimate — track_ocr_characters is
                # repurposed to carry the real billed unit instead of the
                # byte-size heuristic it used to compute independently.
                self.metrics_collector.track_ocr_characters(
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "transliteration":
                self.metrics_collector.track_transliteration_characters(
                    source_lang=source_lang, target_lang=target_lang,
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "language_detection":
                self.metrics_collector.track_language_detection_characters(
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "audio_lang_detection":
                self.metrics_collector.track_audio_lang_detection_length(
                    audio_minutes=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "speaker_diarization":
                self.metrics_collector.track_speaker_diarization_length(
                    audio_minutes=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "language_diarization":
                self.metrics_collector.track_language_diarization_length(
                    audio_minutes=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "ner":
                # billed_input is a CHARACTER count (inference_types.yaml
                # unit: characters), not a word count — track_ner_tokens
                # previously computed len(source.split()) independently;
                # it now carries the same character count billing uses.
                self.metrics_collector.track_ner_tokens(
                    tokens=billed_input, tenant=tenant, service_id=service_id,
                )
        except Exception:
            if self.config.debug:
                logger.debug("Per-service metric emission failed", exc_info=True)
