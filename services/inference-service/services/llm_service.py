"""OpenAI-compatible LLM proxy service."""

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

from ai4i_core.context import (
    set_llm_usage_input_tokens,
    set_llm_usage_model_id,
    set_llm_usage_model_name,
    set_llm_usage_output_tokens,
)
from ai4i_core.observability.utils import get_llm_usage
from config import settings
from inference.inference_server_resolver import InferenceServerResolver
from trace.request_span import traced_span, traced_inference, get_context_attributes


logger = logging.getLogger(__name__)

# Module-level singleton — mirrors the Orchestrator pattern so the TTL cache
# is shared across requests rather than rebuilt on every /chat call.
_resolver = InferenceServerResolver()

# Shared by the buffered, streaming and multipart paths so upstream transport
# failures read identically in the logs whichever entry point hit them.
_UPSTREAM_FAILED_LOG = "LLM upstream request failed (path=%s): %s"

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

    async def forward(self, upstream_url: str, payload: Any) -> Tuple[int, Any]:
        """
        POST ``payload`` to ``upstream_url`` and return (status_code, body).
        Body is parsed as JSON when possible, otherwise returned as
        ``{"raw": <text>}``.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                upstream_url,
                json=payload,
                headers={"Content-Type": "application/json"},
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
    ) -> Tuple[str, str, str, Any]:
        """
        Shared pre-flight for both the buffered and the streaming proxy:

          1. Extract the service ID from the OpenAI `model` field
          2. Resolve endpoint + service_info from MMS (cached)
          3. Tier entitlement check — before any billing span is created
          4. Inject the real upstream model name into payload for vLLM

        Returns ``(url, service_id, model_name, payload)``. Raises
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

        return url, service_id, model_name, payload

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
            url, service_id, model_name, payload = await self._prepare_request(
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

        with traced_span("model") as model_attrs:
            self._seed_model_attrs(model_attrs, service_id, model_name)

            async with traced_inference(payload, _TASK_TYPE_LLM, logger) as infer_attrs:
                # service_id and tenantId must be set explicitly: the PPU Kafka
                # consumer reads only the ai-inference span for billing.
                infer_attrs["service_id"] = service_id
                infer_attrs["tenantId"] = model_attrs.get("tenantId", "")

                logger.info("LLM proxy -> %s (service_id=%s)", url, service_id)
                try:
                    status_code, body = await self.forward(url, payload)
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
                    infer_attrs["output_type"] = "text"
                    # vLLM echoes the real upstream model name in the response —
                    # capture it for the model span (the client's `model` field
                    # carried the service ID, not the upstream model name).
                    model_attrs["model_name"] = body.get("model", "unknown")
                    # Publish to context vars so ObservabilityMiddleware can
                    # emit Prometheus token metrics without re-reading (and
                    # therefore buffering) the response body.
                    set_llm_usage_input_tokens(input_tokens)
                    set_llm_usage_output_tokens(output_tokens)
                    set_llm_usage_model_name(model_attrs["model_name"])

        return status_code, body

    async def open_stream(self, upstream_url: str, payload: Any) -> Tuple[httpx.AsyncClient, httpx.Response]:
        """
        Send ``payload`` to ``upstream_url`` with the response streamed
        rather than buffered, returning the still-open ``(client, response)``
        pair once headers arrive so the caller can inspect
        ``response.status_code`` before committing to a streaming reply.

        Caller owns closing both (see ``_stream_lines``, which does this for
        the success path). Raises ``UpstreamStreamError`` for a 4xx/5xx
        upstream response.

        Uses a connect timeout but no read timeout: ``self.timeout`` is a
        per-read timeout in httpx, and headers arriving fast just pushes the
        wait for the first token into ``aiter_lines`` — a slow model under
        load would otherwise abort the stream mid-response.
        """
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=self.timeout, read=None, write=self.timeout, pool=self.timeout)
        )
        request = client.build_request(
            "POST", upstream_url, json=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = await client.send(request, stream=True)
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

    async def _stream_lines(
        self, client: httpx.AsyncClient, response: httpx.Response
    ) -> AsyncIterator[str]:
        """
        Yield raw SSE lines (blank lines included, to preserve event framing)
        from an already-open streaming response. Closes the client/response
        once the stream ends or the consumer stops iterating early (e.g. the
        browser disconnects).
        """
        try:
            async for line in response.aiter_lines():
                yield line
        finally:
            await response.aclose()
            await client.aclose()

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

    async def proxy_stream(self, path: str, payload: Any) -> Tuple[str, int, Any]:
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
        """
        logger.info("LLM proxy (stream) -> %s", path)
        try:
            client, response = await self.open_stream(path, payload)
        except UpstreamStreamError as exc:
            return "error", exc.status_code, exc.body
        except httpx.RequestError as exc:
            logger.warning(_UPSTREAM_FAILED_LOG, path, exc)
            return "error", 502, {"error": {"message": str(exc), "type": "upstream_error"}}

        async def gen() -> AsyncIterator[str]:
            async for line in self._stream_lines(client, response):
                yield f"{line}\n"

        return "stream", 200, gen()

    async def proxy_traced_stream(
        self,
        path: str,
        payload: Any,
        request: Optional[Any] = None,
    ) -> Tuple[str, int, Any]:
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
        """
        try:
            url, service_id, model_name, payload = await self._prepare_request(
                path=path, payload=payload, request=request,
            )
        except LLMProxyError as exc:
            # Same reasoning as proxy_traced(): no "model" span means no
            # task_type on this trace, so it silently drops out of the logs
            # dashboard's task_types=llm filter. service_id/model_name come
            # off the exception rather than re-deriving from payload again.
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(
                    model_attrs, exc.service_id, exc.model_name, failure_status_code=exc.status_code,
                )
            return "error", exc.status_code, exc.body

        payload = self._with_include_usage(payload)

        kind, status_code, result = await self.proxy_stream(path=url, payload=payload)
        if kind == "error":
            # proxy_stream() failed before gen() (and its own "model" span)
            # was ever created — same gap as above, for a genuine upstream
            # 4xx/5xx or transport error instead of an MMS-level rejection.
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(model_attrs, service_id, model_name, failure_status_code=status_code)
            return "error", status_code, result

        async def gen() -> AsyncIterator[str]:
            with traced_span("model") as model_attrs:
                self._seed_model_attrs(model_attrs, service_id, model_name)
                set_llm_usage_model_name(model_attrs["model_name"])

                async with traced_inference(payload, _TASK_TYPE_LLM, logger) as infer_attrs:
                    # service_id and tenantId must be set explicitly: the PPU
                    # Kafka consumer reads only the ai-inference span for billing.
                    infer_attrs["service_id"] = service_id
                    infer_attrs["tenantId"] = model_attrs.get("tenantId", "")
                    infer_attrs["output_type"] = "text"

                    async for line in result:
                        self._record_stream_usage(line, infer_attrs)
                        yield line

        return "stream", 200, gen()

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
        set_llm_usage_input_tokens(input_tokens)
        set_llm_usage_output_tokens(output_tokens)

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
        is injected from adapter_config before forwarding.
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
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, files=files, data=data)
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
