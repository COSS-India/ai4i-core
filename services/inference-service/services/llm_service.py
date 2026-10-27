"""OpenAI-compatible LLM proxy service."""

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

from ai4i_core.context import (
    get_api_key_id,
    get_application_id,
    get_trace_id,
    set_llm_usage_input_tokens,
    set_llm_usage_model_id,
    set_llm_usage_model_name,
    set_llm_usage_output_tokens,
    set_llm_usage_cached_input_tokens,
)
from ai4i_core.observability.utils import get_llm_cached_tokens, get_llm_usage
from config import settings
from inference.inference_server_resolver import InferenceServerResolver
from services.service_fallback import get_fallbacks
from services.guardrail import (
    GuardrailContext,
    GuardrailError,
    apply_input_guardrail,
    build_guardrail_context,
    process_response_text,
    schedule_audit_log,
)
from trace.request_span import traced_span, traced_inference, get_context_attributes


logger = logging.getLogger(__name__)

# Module-level singleton — mirrors the Orchestrator pattern so the TTL cache
# is shared across requests rather than rebuilt on every /chat call.
_resolver = InferenceServerResolver()

# Shared by the buffered, streaming and multipart paths so upstream transport
# failures read identically in the logs whichever entry point hit them.
_UPSTREAM_FAILED_LOG = "LLM upstream request failed (path=%s): %s"


def _all_unavailable(service_id: str) -> Dict[str, Any]:
    """503 body when the requested service and every configured fallback failed."""
    return {
        "error": {
            "message": f"Service '{service_id}' and its fallback service(s) are unavailable",
            "type": "all_services_unavailable",
        }
    }

# This service only ever proxies OpenAI-compatible LLM calls — task_type is
# never derived per-request (unlike Orchestrator's task services, which read
# it from the client's payload), so it's a fixed fact about which code is
# running rather than a value to compute. _seed_model_attrs() below is the
# single place that stamps it, so success and every rejection path get it
# the same way instead of repeating the literal at each call site.
_TASK_TYPE_LLM = "LLM"


class LLMProxyError(Exception):
    """
    Raised by ``_prepare_request`` when the request cannot proceed (service
    not found, MMS unreachable, tier not entitled). Carries the
    ``(status_code, body)`` the caller should surface, because the buffered
    and streaming entry points return different shapes for the same failure.

    Also carries whatever ``service_id``/``model_name`` ``_prepare_request``
    already knows at the point of rejection, so callers building the
    rejection-branch "model" span read them off the exception instead of
    re-deriving service_id from the raw payload a second time. model_name is
    only ever non-empty for the 403 (tier) case — MMS has already resolved
    it by then; the 404/503 cases fail resolution itself, so it's genuinely
    unknown there and defaults to "" (→ "unknown" in _seed_model_attrs).
    """

    def __init__(self, status_code: int, body: Any, *, service_id: str = "", model_name: str = ""):
        super().__init__(f"llm proxy error {status_code}")
        self.status_code = status_code
        self.body = body
        self.service_id = service_id
        self.model_name = model_name


class UpstreamStreamError(Exception):
    """
    Raised by ``open_stream`` when upstream responds with a 4xx/5xx before
    any SSE body arrives. Error bodies are small and JSON (not SSE), so
    they're read eagerly and surfaced here rather than force-fit into the
    stream, letting callers fall back to a normal JSON error response.
    """

    def __init__(self, status_code: int, body: Any):
        super().__init__(f"upstream returned {status_code}")
        self.status_code = status_code
        self.body = body


class OpenAIProxyService:
    """
    Thin proxy to an OpenAI-compatible upstream LLM server.

    Follows the OpenAI spec: the client sends the model name in ``model``,
    which we treat as the service ID. Resolves the upstream base URL from MMS
    using that model name (the same lookup Triton-backed services do with
    serviceId), appends the OpenAI-compatible path, and forwards the payload.
    """

    def __init__(self) -> None:
        self.timeout = float(settings.LLM_INFERENCE_TIMEOUT)

    async def resolve_upstream_url(self, service_id: str, path: str) -> Tuple[str, Dict[str, Any]]:
        """
        Look up the service in MMS and return (upstream_url, service_info).

        Raises:
            LookupError: service not found in MMS (→ 404)
            ConnectionError: MMS unreachable (→ 503)
            ValueError: endpoint missing in MMS response (→ 503)
        """
        service_info = await _resolver.resolve_service(service_id)

        if not service_info.get("is_published", False):
            raise LookupError(
                f"Service '{service_id}' is not published and cannot be used for inference"
            )

        base = service_info.get("endpoint", "").strip()
        if not base:
            raise ValueError(
                f"No endpoint configured in MMS for service '{service_id}'"
            )
        return f"{base.rstrip('/')}{path}", service_info

    @staticmethod
    def _build_headers(
        service_info: Dict[str, Any], *, content_type: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Build outbound headers for a call to this service's upstream
        endpoint. Adds `Authorization: Bearer <token>` when configured —
        omitted entirely otherwise, so unconfigured services see no change.

        Never log the return value — it may carry the real token.
        """
        headers: Dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = content_type
        token = service_info.get("llm_auth_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def forward(
        self, upstream_url: str, payload: Any, service_info: Dict[str, Any]
    ) -> Tuple[int, Any]:
        """
        POST ``payload`` to ``upstream_url`` and return (status_code, body).
        Body is parsed as JSON when possible, otherwise returned as
        ``{"raw": <text>}``.
        """
        headers = self._build_headers(service_info, content_type="application/json")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                upstream_url,
                json=payload,
                headers=headers,
            )

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        return response.status_code, body

    @staticmethod
    def _enforce_tier_gate(
        service_id: str,
        service_info: Dict[str, Any],
        request: Optional[Any],
        *,
        model_name: str = "",
    ) -> None:
        """
        Reject the request when the caller's tier is not entitled to the
        service. Mirrors orchestrator.py for Triton services, and is only
        enforced when the service has explicit tier assignments.

        ``model_name`` is passed in already-resolved (from _prepare_request,
        which computes it before calling this) so a 403 here still carries
        the real model name on its "model" span instead of "unknown".
        """
        if request is None:
            return
        tier_id = request.headers.get("X-Tier-ID", "")
        if not tier_id:
            return
        allowed_tiers = [str(t) for t in service_info.get("tier_ids", [])]
        if allowed_tiers and tier_id not in allowed_tiers:
            raise LLMProxyError(
                403, {"detail": f"Service '{service_id}' is not available for your quota"},
                service_id=service_id, model_name=model_name,
            )

    async def _prepare_request(
        self,
        path: str,
        payload: Any,
        request: Optional[Any] = None,
    ) -> Tuple[str, str, str, Any, Dict[str, Any]]:
        """
        Shared pre-flight for both the buffered and the streaming proxy:

          1. Extract the service ID from the OpenAI `model` field
          2. Resolve endpoint + service_info from MMS (cached)
          3. Tier entitlement check — before any billing span is created
          4. Inject the real upstream model name into payload for vLLM

        Returns ``(url, service_id, model_name, payload, service_info)`` —
        callers pass ``service_info`` into ``forward()``/``open_stream()`` so
        a configured auth token reaches the outbound headers. Raises
        ``LLMProxyError`` when the request must not reach upstream, so the
        streaming path can never diverge from the buffered path on resolution
        or entitlement (a tier gate that only guards one of the two would let
        clients bypass quota simply by setting ``stream: true``).
        """
        # LLM follows the OpenAI spec: the client sends the model name in
        # `model`, which we treat as the service ID for MMS resolution and PPU
        # billing. The real upstream model is injected from adapter_config in
        # step 4 below, overwriting this before the request reaches vLLM.
        if isinstance(payload, dict):
            service_id = payload.get("model", "") or ""
        else:
            service_id = ""

        # Resolve service from MMS (result is TTL-cached).
        try:
            url, service_info = await self.resolve_upstream_url(service_id=service_id, path=path)
        except LookupError:
            logger.error("LLM service not found: %s", service_id)
            raise LLMProxyError(404, {"detail": f"Service '{service_id}' not found"}, service_id=service_id)
        except (ConnectionError, ValueError):
            logger.error("LLM proxy unavailable for service: %s", service_id)
            raise LLMProxyError(503, {"detail": "LLM service unavailable"}, service_id=service_id)

        # The real upstream model name from MMS adapter_config, replacing the
        # client's `model` value (which was the service ID) with the model
        # vLLM actually expects. Resolved here — before the tier gate, which
        # can itself raise — so a 403 rejection still carries the real model
        # name on its LLMProxyError instead of losing it to "unknown".
        model_name = (service_info.get("adapter_config") or {}).get("model_name", "") if isinstance(payload, dict) else ""

        # Runs before creating billing spans so a 403 produces no ai-inference span.
        self._enforce_tier_gate(service_id, service_info, request, model_name=model_name)

        if model_name and isinstance(payload, dict):
            payload = {**payload, "model": model_name}

        # Registry identity (mm_models.model_id, via MMS) is known as soon as
        # the service resolves — unlike model_name below (the upstream
        # engine's own echoed value, only known after the response) — so set
        # it once here rather than duplicating this in both proxy_traced and
        # proxy_traced_stream. Same task-scoped contextvar->request.state
        # bridge _bridge_llm_usage_to_request() uses for the others.
        set_llm_usage_model_id(service_info.get("model_id") or "")

        return url, service_id, model_name, payload, service_info

    @staticmethod
    def _seed_model_attrs(
        model_attrs: Dict[str, Any],
        service_id: str,
        model_name: Optional[str] = None,
        *,
        failure_status_code: Optional[int] = None,
    ) -> None:
        """
        Stamp the attrs every "model" span carries, regardless of outcome.

        task_type is fixed for this proxy (see _TASK_TYPE_LLM) — every
        caller, success or rejected, funnels through this one place instead
        of repeating the literal, so there's exactly one spot that decides
        how an LLM request's model span is classified.

        ``failure_status_code`` marks a rejection span as failed, mirroring
        ``req_attrs["status"] = "failure"`` in routes/inference.py's request
        span. It matters most for proxy_multipart(), which never opens a
        "request" span — the model span this seeds is the *only* span in
        that trace, so without this it carries task_type but nothing marking
        the request as failed, e.g. for a rejected/never-forwarded audio
        upload. Success spans (the default, param omitted) are unaffected —
        the model span has never carried a status attribute on that path,
        and this doesn't change that.
        """
        model_attrs["task_type"] = _TASK_TYPE_LLM
        model_attrs["model_name"] = model_name or "unknown"
        model_attrs["model_version"] = "unknown"
        model_attrs.update(get_context_attributes())
        model_attrs["service_id"] = service_id
        if failure_status_code is not None:
            model_attrs["status"] = "failure"
            model_attrs["status_code"] = failure_status_code

    async def proxy_traced(
        self,
        path: str,
        payload: Any,
        request: Optional[Any] = None,
    ) -> Tuple[int, Any]:
        """
        Full LLM proxy with MMS resolution, tier gate, and OTel spans.

        Order matches the Orchestrator + BaseTaskService pattern: steps 1-4
        run in ``_prepare_request`` (shared with the streaming path), then
        model + ai-inference spans wrap the actual forward.
        """
        try:
            url, service_id, model_name, payload, service_info = await self._prepare_request(
                path=path, payload=payload, request=request,
            )
        except LLMProxyError as exc:
            # A rejection here (404/403/503) means resolution never reached
            # the point of opening a "model" span below — but the telemetry
            # dashboard's task_type comes exclusively from that span, so
            # without one this trace would show task_type=null and never
            # match a task_types=llm filter. Emit a minimal model span, seeded
            # the same way as the success span below, so the failure is still
            # classifiable as an LLM request. service_id/model_name come off
            # the exception (whatever _prepare_request already resolved)
            # rather than re-deriving service_id from payload a second time.
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(
                    model_attrs, exc.service_id, exc.model_name, failure_status_code=exc.status_code,
                )
            return exc.status_code, exc.body

        # ── PII guardrail: build context + mask input ─────────────────────
        app_id = get_application_id()
        guardrail_ctx = GuardrailContext()
        try:
            guardrail_ctx = await build_guardrail_context(app_id)
        except GuardrailError as exc:
            logger.error("PII policy evaluation failed, blocking request: %s", exc)
            schedule_audit_log(
                ctx=guardrail_ctx,
                trace_id=get_trace_id(),
                model_request=payload,
                response={},
                app_id=app_id,
                status_code=503,
            )
            return 503, {"error": {"message": "Request blocked: PII policy could not be evaluated", "type": "guardrail_error"}}
        if guardrail_ctx.active:
            logger.info("══ GUARDRAIL REQUEST (app_id=%s) ══════════════", app_id)
            try:
                payload = await asyncio.to_thread(apply_input_guardrail, payload, guardrail_ctx)
            except GuardrailError as exc:
                logger.error("PII input masking failed, blocking request: %s", exc)
                schedule_audit_log(
                    ctx=guardrail_ctx,
                    trace_id=get_trace_id(),
                    model_request=payload,
                    response={},
                    app_id=app_id,
                    status_code=503,
                )
                return 503, {"error": {"message": "Request blocked: PII policy enforcement failed", "type": "guardrail_error"}}
            logger.info("Scope: %s", guardrail_ctx.scopes)
        # ─────────────────────────────────────────────────────────────────

        status_code, body = await self._forward_traced(path, url, service_id, model_name, payload, service_info)
        if status_code >= 500:
            # The model server is unreachable or failed: the Application's
            # fallbacks for it, in order. A 4xx is the client's and is returned.
            tried = False
            async for fb_id, fb_url, fb_model, fb_payload, fb_info in self._fallbacks_for(
                path, payload, service_id, request, status_code
            ):
                tried = True
                status_code, body = await self._forward_traced(path, fb_url, fb_id, fb_model, fb_payload, fb_info)
                if status_code < 500:
                    if request is not None:
                        request.state.service_id = fb_id
                    break
            if tried and status_code >= 500:
                # Metrics label the failed request with the requested model,
                # not the last fallback _prepare_request resolved.
                set_llm_usage_model_id(service_info.get("model_id") or "")
                status_code, body = 503, _all_unavailable(service_id)

        # ── PII guardrail: process response + fire-and-forget audit log ───
        if guardrail_ctx.active:
            if status_code == 200 and isinstance(body, dict):
                try:
                    choices = body.get("choices") or []
                    if choices and isinstance((choices[0].get("message") or {}).get("content"), str):
                        content = choices[0]["message"]["content"]
                        content = await asyncio.to_thread(process_response_text, content, guardrail_ctx)
                        body = {
                            **body,
                            "choices": [
                                {**choices[0], "message": {**choices[0]["message"], "content": content}},
                                *choices[1:],
                            ],
                        }
                except Exception:
                    logger.error("Guardrail response processing failed, blocking response", exc_info=True)
                    schedule_audit_log(
                        ctx=guardrail_ctx,
                        trace_id=get_trace_id(),
                        model_request=payload,
                        response={},
                        app_id=app_id,
                        status_code=500,
                    )
                    return 500, {"error": {"message": "Response blocked: PII policy enforcement failed", "type": "guardrail_error"}}
            schedule_audit_log(
                ctx=guardrail_ctx,
                trace_id=get_trace_id(),
                model_request=payload,
                response=body,
                app_id=app_id,
                status_code=status_code,
            )
        # ─────────────────────────────────────────────────────────────────

        return status_code, body

    async def _forward_traced(
        self,
        path: str,
        url: str,
        service_id: str,
        model_name: str,
        payload: Any,
        service_info: Dict[str, Any],
    ) -> Tuple[int, Any]:
        """One upstream call inside its own model + ai-inference spans, so a
        fallback attempt is traced (and billed) exactly like the requested
        service."""
        with traced_span("model") as model_attrs:
            self._seed_model_attrs(model_attrs, service_id, model_name)

            async with traced_inference(payload, _TASK_TYPE_LLM, logger) as infer_attrs:
                # service_id, tenantId and model_name must be set explicitly:
                # the PPU Kafka consumer reads only the ai-inference span.
                infer_attrs["service_id"] = service_id
                infer_attrs["tenantId"] = model_attrs.get("tenantId", "")
                infer_attrs["model_name"] = model_attrs["model_name"]

                logger.info("LLM proxy -> %s (service_id=%s)", url, service_id)
                try:
                    status_code, body = await self.forward(url, payload, service_info)
                except httpx.RequestError as exc:
                    logger.warning(_UPSTREAM_FAILED_LOG, path, exc)
                    # traced_span only marks the span "failure" when an
                    # exception propagates out of the `with` block; returning
                    # here instead of raising would otherwise exit through the
                    # success branch and mismark this span 200/success even
                    # though the request never reached upstream.
                    infer_attrs["status"] = "failure"
                    infer_attrs["status_code"] = 502
                    return 502, {"detail": "Upstream LLM request failed"}

                if status_code >= 400:
                    # Same reasoning as above: a real upstream 4xx/5xx doesn't
                    # raise, so the span must be marked failed explicitly or
                    # it silently reports success to the metering/logs pipeline.
                    infer_attrs["status"] = "failure"
                    infer_attrs["status_code"] = status_code
                    if isinstance(body, dict):
                        message = (
                            body.get("detail")
                            or (body.get("error") or {}).get("message")
                            or body.get("message")
                            or "Upstream LLM error"
                        )
                        body = {"detail": message}

                if isinstance(body, dict):
                    input_tokens, output_tokens = get_llm_usage(body)
                    infer_attrs["input_tokens"] = input_tokens
                    infer_attrs["output_tokens"] = output_tokens
                    # Part of input_tokens served from vLLM's prefix cache;
                    # the PPU consumer prices it at the cached input price.
                    infer_attrs["cached_input_tokens"] = get_llm_cached_tokens(body)
                    infer_attrs["output_type"] = "text"
                    # vLLM echoes the real upstream model name in the response —
                    # capture it for the model span (the client's `model` field
                    # carried the service ID, not the upstream model name).
                    model_attrs["model_name"] = body.get("model", "unknown")
                    infer_attrs["model_name"] = model_attrs["model_name"]
                    # Publish to context vars so ObservabilityMiddleware can
                    # emit Prometheus token metrics without re-reading (and
                    # therefore buffering) the response body.
                    set_llm_usage_input_tokens(input_tokens)
                    set_llm_usage_output_tokens(output_tokens)
                    set_llm_usage_cached_input_tokens(infer_attrs["cached_input_tokens"])
                    set_llm_usage_model_name(model_attrs["model_name"])

        return status_code, body

    async def _fallbacks_for(
        self, path: str, payload: Any, service_id: str, request: Optional[Any], upstream_status: int
    ):
        """The Application's fallbacks for ``service_id`` that still resolve and
        pass the Tier gate, each prepared like the requested service (same
        messages, ``model`` = the fallback's upstream model name)."""
        if not isinstance(payload, dict):
            return
        for fallback_id in await get_fallbacks(service_id):
            try:
                url, _, model_name, fb_payload, service_info = await self._prepare_request(
                    path=path, payload={**payload, "model": fallback_id}, request=request,
                )
            except LLMProxyError as exc:  # unknown, unpublished or out of Tier: skip it
                logger.warning(
                    "service_fallback_skipped fallback_service_id=%s status=%s", fallback_id, exc.status_code
                )
                continue
            logger.warning(
                "service_failover application_id=%s api_key_id=%s requested_service_id=%s "
                "fallback_service_id=%s reason=upstream_%s",
                get_application_id() or "", get_api_key_id() or "", service_id, fallback_id, upstream_status,
            )
            yield fallback_id, url, model_name, fb_payload, service_info


    async def open_stream(
        self, upstream_url: str, payload: Any, service_info: Dict[str, Any]
    ) -> Tuple[httpx.AsyncClient, httpx.Response]:
        """
        Send ``payload`` to ``upstream_url`` with the response streamed
        rather than buffered, returning the still-open ``(client, response)``
        pair once headers arrive so the caller can inspect
        ``response.status_code`` before committing to a streaming reply.

        Caller owns closing both (proxy_stream does this for the success
        path). Raises ``UpstreamStreamError`` for a 4xx/5xx upstream response.

        No httpx read timeout: ``self.timeout`` is per read in httpx, and a
        slow model under load would otherwise abort the stream mid-response.
        Only the start is time-limited — the response headers here, the
        first line in proxy_stream — so a server that accepts the connection
        and sends nothing raises ``httpx.ReadTimeout`` instead of hanging,
        and the request can still fail over.
        """
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=self.timeout, read=None, write=self.timeout, pool=self.timeout)
        )
        headers = self._build_headers(service_info, content_type="application/json")
        request = client.build_request(
            "POST", upstream_url, json=payload,
            headers=headers,
        )
        try:
            response = await asyncio.wait_for(client.send(request, stream=True), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            await client.aclose()
            raise httpx.ReadTimeout("LLM upstream sent no response headers in time") from exc
        except Exception:
            await client.aclose()
            raise

        if response.status_code >= 400:
            raw = await response.aread()
            await response.aclose()
            await client.aclose()
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw.decode("utf-8", errors="replace")}
            raise UpstreamStreamError(response.status_code, body)

        return client, response

    @staticmethod
    def _with_include_usage(payload: Any) -> Any:
        """
        Return ``payload`` with ``stream_options.include_usage`` requested.

        Token counts otherwise never arrive on the streaming path, so PPU
        billing and metering would silently record zeros. Server-side
        ``setdefault`` semantics: an explicit client value (including
        ``False``) is honoured, and a non-dict ``stream_options`` is replaced
        rather than crashing on ``.setdefault``.
        """
        if not isinstance(payload, dict):
            return payload
        stream_options = payload.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}
        else:
            stream_options = dict(stream_options)
        stream_options.setdefault("include_usage", True)
        return {**payload, "stream_options": stream_options}

    async def proxy_stream(
        self, path: str, payload: Any, service_info: Dict[str, Any]
    ) -> Tuple[str, int, Any]:
        """
        Streaming counterpart to ``forward()``. Opens the upstream connection
        and returns one of:
          ("error", status_code, body)     - upstream failure
          ("stream", 200, async_generator) - success; generator yields raw
              SSE lines (each with a trailing "\\n"), passed through
              unchanged from upstream and terminated by its own
              "data: [DONE]" event.

        Upstream is expected to already be an OpenAI-spec SSE emitter
        (vLLM/gemma server), so this passes bytes through rather than
        re-parsing and re-serializing each chunk.

        The stream only counts as started once its first line arrives within
        ``self.timeout`` (the headers are limited in open_stream). Until then
        nothing has reached the client, so a hung upstream is a 502 "error"
        the caller can still fail over; after it there is no read limit.
        """
        logger.info("LLM proxy (stream) -> %s", path)
        try:
            client, response = await self.open_stream(path, payload, service_info)
        except UpstreamStreamError as exc:
            return "error", exc.status_code, exc.body
        except httpx.RequestError as exc:
            logger.warning(_UPSTREAM_FAILED_LOG, path, exc)
            return "error", 502, {"error": {"message": str(exc), "type": "upstream_error"}}

        lines = response.aiter_lines()
        try:
            first_line: Optional[str] = await asyncio.wait_for(lines.__anext__(), timeout=self.timeout)
        except StopAsyncIteration:
            first_line = None
        except (asyncio.TimeoutError, httpx.RequestError) as exc:
            await response.aclose()
            await client.aclose()
            logger.warning(_UPSTREAM_FAILED_LOG, path, type(exc).__name__)
            return "error", 502, {
                "error": {"message": "Upstream LLM stream did not start in time", "type": "upstream_error"}
            }

        async def gen() -> AsyncIterator[str]:
            # Raw SSE lines, blank lines included (they frame events); closes
            # the client/response once the stream ends or the consumer stops
            # iterating early (e.g. the browser disconnects).
            try:
                if first_line is not None:
                    yield f"{first_line}\n"
                async for line in lines:
                    yield f"{line}\n"
            finally:
                await response.aclose()
                await client.aclose()

        return "stream", 200, gen()

    async def proxy_traced_stream(
        self,
        path: str,
        payload: Any,
        request: Optional[Any] = None,
    ) -> Tuple[str, int, Any, Optional[Dict[str, str]]]:
        """
        Streaming counterpart to ``proxy_traced()``. Shares
        ``_prepare_request`` with it, so MMS resolution, the tier gate and the
        upstream model-name injection behave identically whether the client
        asked for a stream or not.

        On the "stream" path the spans are opened lazily inside the returned
        generator and only finalize once the caller fully iterates it (i.e.
        once the client has read the whole SSE response) — callers must
        consume it to completion, not just discard it, or the ai-inference
        span used for PPU billing never gets logged.

        On the "error" path, the caller (``_run_llm_chat_stream`` in
        routes/inference.py) opens its "request" span only *after* this
        method returns — so a "model" span created eagerly in here, before
        that "request" span exists, has no parent in the active OTel context
        and exports as its own disconnected root (different otel_trace_id
        than its sibling "request" span). This method therefore does NOT
        open a "model" span for either error branch itself; it instead
        returns ``model_ctx`` — {"service_id", "model_name"} — as the 4th
        tuple element (``None`` for the "stream" kind) so the caller can
        build that span from inside its already-open "request" span, keeping
        the tree intact. The dashboard is unaffected either way (it groups
        by correlation_id, not OTel parent linkage), but the raw trace data
        is now consistent.
        """
        try:
            url, service_id, model_name, payload, service_info = await self._prepare_request(
                path=path, payload=payload, request=request,
            )
        except LLMProxyError as exc:
            model_ctx = {"service_id": exc.service_id, "model_name": exc.model_name}
            return "error", exc.status_code, exc.body, model_ctx

        # ── PII guardrail: mask input before opening stream ───────────────
        app_id = get_application_id()
        guardrail_ctx = GuardrailContext()
        try:
            guardrail_ctx = await build_guardrail_context(app_id)
        except GuardrailError as exc:
            logger.error("PII policy evaluation failed, blocking stream request: %s", exc)
            schedule_audit_log(
                ctx=guardrail_ctx,
                trace_id=get_trace_id(),
                model_request=payload,
                response={},
                app_id=app_id,
                status_code=503,
            )
            model_ctx = {"service_id": service_id, "model_name": model_name}
            return "error", 503, {"error": {"message": "Request blocked: PII policy could not be evaluated", "type": "guardrail_error"}}, model_ctx
        if guardrail_ctx.active:
            try:
                payload = await asyncio.to_thread(apply_input_guardrail, payload, guardrail_ctx)
            except GuardrailError as exc:
                logger.error("PII input masking failed, blocking stream request: %s", exc)
                schedule_audit_log(
                    ctx=guardrail_ctx,
                    trace_id=get_trace_id(),
                    model_request=payload,
                    response={},
                    app_id=app_id,
                    status_code=503,
                )
                model_ctx = {"service_id": service_id, "model_name": model_name}
                return "error", 503, {"error": {"message": "Request blocked: PII policy enforcement failed", "type": "guardrail_error"}}, model_ctx
        # ─────────────────────────────────────────────────────────────────

        payload = self._with_include_usage(payload)

        # The request / model / ai-inference spans open only once the stream
        # has started (inside the generators below), so they measure from
        # here, or they would leave out the wait for the first token.
        started_at = time.time()
        kind, status_code, result = await self.proxy_stream(path=url, payload=payload, service_info=service_info)
        if kind == "error" and status_code >= 500:
            # Nothing has reached the client yet, so the stream can still move
            # to a fallback; once a stream has started it is never switched.
            tried = False
            async for fb_id, fb_url, fb_model, fb_payload, fb_info in self._fallbacks_for(
                path, payload, service_id, request, status_code
            ):
                tried = True
                kind, status_code, result = await self.proxy_stream(path=fb_url, payload=fb_payload, service_info=fb_info)
                if kind == "stream" or status_code < 500:
                    service_id, model_name, payload, service_info = fb_id, fb_model, fb_payload, fb_info
                    if request is not None:
                        request.state.service_id = fb_id
                    break
            if tried and kind == "error" and status_code >= 500:
                set_llm_usage_model_id(service_info.get("model_id") or "")
                status_code, result = 503, _all_unavailable(service_id)
        if kind == "error":
            if guardrail_ctx.active:
                schedule_audit_log(
                    ctx=guardrail_ctx,
                    trace_id=get_trace_id(),
                    model_request=payload,
                    response=result,
                    app_id=app_id,
                    status_code=status_code,
                )
            model_ctx = {"service_id": service_id, "model_name": model_name}
            return "error", status_code, result, model_ctx

        async def gen() -> AsyncIterator[str]:
            with traced_span("model", start_time=started_at) as model_attrs:
                self._seed_model_attrs(model_attrs, service_id, model_name)
                set_llm_usage_model_name(model_attrs["model_name"])

                async with traced_inference(
                    payload, _TASK_TYPE_LLM, logger, start_time=started_at
                ) as infer_attrs:
                    # service_id, tenantId and model_name must be set explicitly:
                    # the PPU Kafka consumer reads only the ai-inference span.
                    infer_attrs["service_id"] = service_id
                    infer_attrs["tenantId"] = model_attrs.get("tenantId", "")
                    infer_attrs["model_name"] = model_attrs["model_name"]
                    infer_attrs["output_type"] = "text"

                    if not guardrail_ctx.active:
                        # No guardrail — pass lines through unchanged.
                        async for line in result:
                            self._record_stream_usage(line, infer_attrs)
                            yield line
                    else:
                        # Guardrail active — buffer full content, process, re-emit.
                        # PII masking requires the complete text; streaming is
                        # sacrificed for correctness when a policy is applied.
                        full_content: list[str] = []
                        last_chunk: Optional[Dict[str, Any]] = None
                        async for line in result:
                            self._record_stream_usage(line, infer_attrs)
                            if line.startswith("data:"):
                                data = line[len("data:"):].strip()
                                if data and data != "[DONE]":
                                    try:
                                        chunk = json.loads(data)
                                        delta_content = (
                                            (chunk.get("choices") or [{}])[0]
                                            .get("delta", {})
                                            .get("content") or ""
                                        )
                                        if delta_content:
                                            full_content.append(delta_content)
                                        last_chunk = chunk
                                    except Exception:
                                        pass

                        # Process the complete reconstructed response text.
                        raw_content = "".join(full_content)
                        processed = await asyncio.to_thread(process_response_text, raw_content, guardrail_ctx)

                        if last_chunk is not None:
                            choices = last_chunk.get("choices") or [{}]
                            synthetic = {
                                **last_chunk,
                                "choices": [{
                                    **choices[0],
                                    "delta": {"content": processed, "role": "assistant"},
                                    "finish_reason": "stop",
                                }],
                            }
                            yield f"data: {json.dumps(synthetic)}\n\n"
                            schedule_audit_log(
                                ctx=guardrail_ctx,
                                trace_id=get_trace_id(),
                                model_request=payload,
                                response=synthetic,
                                app_id=app_id,
                                status_code=200,
                            )
                        else:
                            schedule_audit_log(
                                ctx=guardrail_ctx,
                                trace_id=get_trace_id(),
                                model_request=payload,
                                response={},
                                app_id=app_id,
                                status_code=200,
                            )
                        yield "data: [DONE]\n\n"

        # 4th element on success: when the stream was requested, for the
        # route's "request" span (opened once the client starts reading).
        return "stream", 200, gen(), {"started_at": started_at}

    @staticmethod
    def _record_stream_usage(line: str, infer_attrs: Dict[str, Any]) -> None:
        """
        Parse one raw SSE line and, when it carries a ``usage`` block, record
        the token counts onto the ai-inference span and the context vars.

        ``get_llm_usage()`` returns (0, 0) both when a chunk carries no
        ``usage`` block at all (every normal content-delta chunk) and when it
        carries a genuinely all-zero one (e.g. a request rejected/truncated
        before producing tokens). Checking the block's presence directly,
        instead of the truthiness of the extracted counts, tells those apart
        so a real zero-token usage chunk still gets recorded.
        """
        if not line.startswith("data:"):
            return
        data = line[len("data:"):].strip()
        if not data or data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except Exception:
            return
        if not (isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict)):
            return

        input_tokens, output_tokens = get_llm_usage(chunk)
        infer_attrs["input_tokens"] = input_tokens
        infer_attrs["output_tokens"] = output_tokens
        infer_attrs["cached_input_tokens"] = get_llm_cached_tokens(chunk)
        set_llm_usage_input_tokens(input_tokens)
        set_llm_usage_output_tokens(output_tokens)
        set_llm_usage_cached_input_tokens(infer_attrs["cached_input_tokens"])

    async def proxy_multipart(
        self,
        path: str,
        *,
        files: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
        request: Optional[Any] = None,
    ) -> Tuple[int, Any]:
        """
        Forward a ``multipart/form-data`` POST. Used by the /audio/*
        passthrough routes — kept separate from ``proxy_traced()`` so the JSON
        path stays 1:1 unchanged.

        ``files`` is the ``{field_name: (filename, bytes, content_type)}``
        dict that ``httpx.AsyncClient.post`` expects. ``data`` carries the
        non-file form fields (e.g. ``language``, …).

        Endpoint resolution uses MMS via the `model` form field — the OpenAI
        service identifier (same as JSON routes). The real upstream model name
        is injected from adapter_config before forwarding. If that upstream is
        unreachable (transport error / 5xx) the upload moves to the
        Application's fallbacks for the service, like the JSON routes.
        """
        data = dict(data or {})
        service_id = data.get("model", "") or ""

        # Resolve service from MMS (result is TTL-cached).
        try:
            url, service_info = await self.resolve_upstream_url(service_id=service_id, path=path)
        except LookupError:
            logger.error("LLM audio service not found: %s", service_id)
            # proxy_multipart never opens a "request" span (see routes calling
            # it), so this model span is the ONLY span in the trace — without
            # a failure marking here, the whole request is untraceable as
            # failed anywhere in the pipeline.
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(model_attrs, service_id, failure_status_code=404)
            return 404, {"error": {"message": f"Service '{service_id}' not found", "type": "not_found"}}
        except (ConnectionError, ValueError):
            logger.error("LLM audio proxy unavailable for service: %s", service_id)
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(model_attrs, service_id, failure_status_code=503)
            return 503, {"error": {"message": "Service unavailable", "type": "api_error"}}

        # The real upstream model name from MMS adapter_config — resolved
        # here, before the tier gate, so a 403 rejection's model span still
        # carries it instead of "unknown" (service_info already has it;
        # mirrors _prepare_request's ordering for the JSON entry points).
        model_name = (service_info.get("adapter_config") or {}).get("model_name", "")

        # Tier entitlement check. Only enforced when service has explicit tier assignments.
        if request is not None:
            tier_id = request.headers.get("X-Tier-ID", "")
            if tier_id:
                allowed_tiers = [str(t) for t in service_info.get("tier_ids", [])]
                if allowed_tiers and tier_id not in allowed_tiers:
                    with traced_span("model") as model_attrs:
                        self._seed_model_attrs(model_attrs, service_id, model_name, failure_status_code=403)
                    return 403, {"error": {
                        "message": f"Service '{service_id}' is not available for your quota",
                        "type": "permission_error",
                    }}

        # Inject the resolved model name into the outgoing form data.
        if model_name:
            data["model"] = model_name
        model = data.get("model", "")

        with traced_span("model") as model_attrs:
            self._seed_model_attrs(model_attrs, service_id, model)

        logger.info("LLM proxy (multipart) -> %s (service_id=%s)", url, service_id)
        status_code, body = await self._post_multipart(path, url, files, data, service_info)
        if status_code >= 500:
            # Same rule as the JSON routes: only an unreachable model moves the
            # upload to the Application's fallbacks. The file bytes are in
            # memory, so every fallback gets the same upload.
            tried = False
            async for fb_id, fb_url, fb_model, fb_data, fb_info in self._fallbacks_for(
                path, data, service_id, request, status_code
            ):
                tried = True
                with traced_span("model") as fb_model_attrs:
                    self._seed_model_attrs(fb_model_attrs, fb_id, fb_model)
                status_code, body = await self._post_multipart(path, fb_url, files, fb_data, fb_info)
                if status_code < 500:
                    if request is not None:
                        request.state.service_id = fb_id
                    break
            if tried and status_code >= 500:
                # Metrics label the failed request with the requested model,
                # not the last fallback _prepare_request resolved.
                set_llm_usage_model_id(service_info.get("model_id") or "")
                status_code, body = 503, _all_unavailable(service_id)
        return status_code, body

    async def _post_multipart(
        self,
        path: str,
        url: str,
        files: Dict[str, Any],
        data: Dict[str, Any],
        service_info: Dict[str, Any],
    ) -> Tuple[int, Any]:
        """One multipart upload to ``url``; a transport failure is a 502."""
        # No content_type override: httpx computes the multipart boundary
        # Content-Type itself from `files`, as long as headers doesn't
        # already set one — _build_headers only ever adds Authorization.
        headers = self._build_headers(service_info)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, files=files, data=data, headers=headers)
        except httpx.RequestError as exc:
            logger.warning(
                _UPSTREAM_FAILED_LOG, path, exc
            )
            return 502, {
                "error": {"message": str(exc), "type": "upstream_error"}
            }

        try:
            return response.status_code, response.json()
        except Exception:
            # Non-JSON 200 (response_format=text) or non-JSON error body
            # — return the raw text so the route layer can decide how to
            # surface it (text/plain vs JSON-wrapped).
            return response.status_code, response.text
