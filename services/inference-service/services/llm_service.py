"""OpenAI-compatible LLM proxy service."""

import json
import logging
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import httpx

from ai4i_core.context import (
    set_llm_usage_input_tokens,
    set_llm_usage_model_name,
    set_llm_usage_output_tokens,
)
from ai4i_core.observability.utils import get_llm_usage
from config import settings
from services.service_registry import service_id_resolver
from trace.request_span import traced_span, traced_inference, get_context_attributes

logger = logging.getLogger(__name__)


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

    Resolves the upstream base URL from ``LLM_MODEL_ENDPOINTS[model]`` (if set)
    or ``LLM_DEFAULT_ENDPOINT``, appends the OpenAI-compatible path, and forwards
    the JSON payload unchanged.
    """

    def __init__(self) -> None:
        self.timeout = float(settings.LLM_INFERENCE_TIMEOUT)
        self.model_endpoints: Dict[str, str] = settings.LLM_MODEL_ENDPOINTS or {}
        self.default_endpoint: str = (settings.LLM_DEFAULT_ENDPOINT or "").strip()

    def resolve_upstream_url(self, model: Optional[str], path: str) -> str:
        base = self.model_endpoints.get(model) if model else None
        base = (base or self.default_endpoint or "").strip()
        if not base:
            raise ValueError(
                "No upstream LLM endpoint configured. Set LLM_DEFAULT_ENDPOINT "
                "or LLM_MODEL_ENDPOINTS for the requested model."
            )
        return f"{base.rstrip('/')}{path}"

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

    async def proxy_traced(self, path: str, payload: Any) -> Tuple[int, Any]:
        """
        proxy() wrapped with model + ai_inference spans, mirroring the
        Orchestrator + BaseTaskService pattern used by Triton-backed services.
        The caller (route) owns the outer request span.
        """
        # Extract before forwarding — upstream LLM API doesn't accept this field.
        # Mirror orchestrator: check config block first, then top-level.
        if isinstance(payload, dict):
            config_block = payload.get("config") or {}
            service_id = (
                             config_block.get("serviceId") if isinstance(config_block, dict) else None
                         ) or payload.get("serviceId", "") or ""
            payload.pop("serviceId", None)
        else:
            service_id = ""

        # OpenAI clients send `model`, not `serviceId`. Resolve the registered
        # service_id from the model name so PPU billing/metering have a key.
        if not service_id and isinstance(payload, dict):
            service_id = await service_id_resolver.resolve(payload.get("model", ""))

        with traced_span("model") as model_attrs:
            model_attrs["task_type"] = "LLM"
            model_attrs["model_name"] = payload.get("model", "unknown") if isinstance(payload, dict) else "unknown"
            model_attrs["model_version"] = "unknown"
            model_attrs.update(get_context_attributes())
            model_attrs["service_id"] = service_id
            set_llm_usage_model_name(model_attrs["model_name"])

            async with traced_inference(payload, "LLM", logger) as infer_attrs:
                # service_id is not in context vars — must be copied explicitly.
                # tenantId is also set explicitly: the PPU Kafka consumer reads only
                # the ai-inference span for billing, so it must always be present
                # even if the contextvar is None (get_context_attributes skips None).
                infer_attrs["service_id"] = service_id
                infer_attrs["tenantId"] = model_attrs.get("tenantId", "")

                status_code, body = await self.proxy(path=path, payload=payload)

                if isinstance(body, dict):
                    infer_attrs["input_tokens"], infer_attrs["output_tokens"] = get_llm_usage(body)
                    infer_attrs["output_type"] = "text"
                    set_llm_usage_input_tokens(infer_attrs["input_tokens"])
                    set_llm_usage_output_tokens(infer_attrs["output_tokens"])

        return status_code, body

    async def proxy(self, path: str, payload: Any) -> Tuple[int, Any]:
        """
        Resolve upstream from ``payload['model']`` and forward.

        Maps known failure modes to OpenAI-style error responses:
          - misconfiguration (no endpoint set) -> 503
          - upstream network/transport error    -> 502
        Any other 4xx/5xx from the upstream is passed through unchanged.
        """
        model = payload.get("model") if isinstance(payload, dict) else None
        try:
            url = self.resolve_upstream_url(model=model, path=path)
        except ValueError as exc:
            logger.error("LLM proxy misconfiguration: %s", exc)
            return 503, {"detail": str(exc)}

        logger.info("LLM proxy -> %s (model=%s)", url, model)
        try:
            return await self.forward(url, payload)
        except httpx.RequestError as exc:
            logger.warning("LLM upstream request failed (path=%s): %s", path, exc)
            return 502, {"error": {"message": str(exc), "type": "upstream_error"}}

    async def open_stream(self, upstream_url: str, payload: Any) -> Tuple[httpx.AsyncClient, httpx.Response]:
        """
        Send ``payload`` to ``upstream_url`` with the response streamed
        rather than buffered, returning the still-open ``(client,
        response)`` pair once headers arrive so the caller can inspect
        ``response.status_code`` before committing to a streaming reply.

        Caller owns closing both (see ``_stream_lines``, which does this
        for the success path). Raises ``UpstreamStreamError`` for a
        4xx/5xx upstream response.

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
        Yield raw SSE lines (blank lines included, to preserve event
        framing) from an already-open streaming response. Closes the
        client/response once the stream ends or the consumer stops
        iterating early (e.g. the browser disconnects).
        """
        try:
            async for line in response.aiter_lines():
                yield line
        finally:
            await response.aclose()
            await client.aclose()

    async def proxy_stream(self, path: str, payload: Any) -> Tuple[str, int, Any]:
        """
        Streaming counterpart to ``proxy()``. Resolves upstream, opens the
        connection, and returns one of:
          ("error", status_code, body)     - misconfig / upstream failure
          ("stream", 200, async_generator) - success; generator yields raw
              SSE lines (each with a trailing "\\n"), passed through
              unchanged from upstream and terminated by its own
              "data: [DONE]" event.

        Upstream is expected to already be an OpenAI-spec SSE emitter
        (vLLM/gemma server) — this passes bytes through rather than
        re-parsing and re-serializing each chunk.
        """
        model = payload.get("model") if isinstance(payload, dict) else None
        try:
            url = self.resolve_upstream_url(model=model, path=path)
        except ValueError as exc:
            logger.error("LLM proxy misconfiguration: %s", exc)
            return "error", 503, {"detail": str(exc)}

        logger.info("LLM proxy (stream) -> %s (model=%s)", url, model)
        try:
            client, response = await self.open_stream(url, payload)
        except UpstreamStreamError as exc:
            return "error", exc.status_code, exc.body
        except httpx.RequestError as exc:
            logger.warning("LLM upstream request failed (path=%s): %s", path, exc)
            return "error", 502, {"error": {"message": str(exc), "type": "upstream_error"}}

        async def gen() -> AsyncIterator[str]:
            async for line in self._stream_lines(client, response):
                yield f"{line}\n"

        return "stream", 200, gen()

    async def proxy_traced_stream(self, path: str, payload: Any) -> Tuple[str, int, Any]:
        """
        proxy_stream() wrapped with model + ai_inference spans, mirroring
        proxy_traced(). On the "stream" path the spans are opened lazily
        inside the returned generator and only finalize once the caller
        fully iterates it (i.e. once the client has read the whole SSE
        response) — callers must consume it to completion, not just
        discard it, or the ai-inference span (used for PPU billing) never
        gets logged.

        Requests ``stream_options.include_usage`` (an OpenAI-spec field)
        when the caller hasn't set it, since usage/token counts otherwise
        only arrive in a non-streaming response body.
        """
        if isinstance(payload, dict):
            config_block = payload.get("config") or {}
            service_id = (
                             config_block.get("serviceId") if isinstance(config_block, dict) else None
                         ) or payload.get("serviceId", "") or ""
            payload.pop("serviceId", None)
            stream_options = payload.setdefault("stream_options", {})
            if not isinstance(stream_options, dict):
                stream_options = {}
                payload["stream_options"] = stream_options
            stream_options.setdefault("include_usage", True)
        else:
            service_id = ""

        # OpenAI clients send `model`, not `serviceId`. Resolve the registered
        # service_id from the model name so PPU billing/metering have a key.
        if not service_id and isinstance(payload, dict):
            service_id = await service_id_resolver.resolve(payload.get("model", ""))

        kind, status_code, result = await self.proxy_stream(path=path, payload=payload)
        if kind == "error":
            return "error", status_code, result

        model = payload.get("model", "unknown") if isinstance(payload, dict) else "unknown"

        async def gen() -> AsyncIterator[str]:
            with traced_span("model") as model_attrs:
                model_attrs["task_type"] = "LLM"
                model_attrs["model_name"] = model
                model_attrs["model_version"] = "unknown"
                model_attrs.update(get_context_attributes())
                model_attrs["service_id"] = service_id
                set_llm_usage_model_name(model_attrs["model_name"])

                async with traced_inference(payload, "LLM", logger) as infer_attrs:
                    infer_attrs["service_id"] = service_id
                    infer_attrs["tenantId"] = model_attrs.get("tenantId", "")
                    infer_attrs["output_type"] = "text"

                    async for line in result:
                        if line.startswith("data:"):
                            data = line[len("data:"):].strip()
                            if data and data != "[DONE]":
                                try:
                                    chunk = json.loads(data)
                                except Exception:
                                    chunk = None
                                # get_llm_usage() returns (0, 0) both when a chunk
                                # carries no `usage` block at all (every normal
                                # content-delta chunk) and when it carries a
                                # genuinely all-zero one (e.g. a request rejected/
                                # truncated before producing tokens) — checking the
                                # block's presence directly, instead of truthiness
                                # of the extracted counts, tells those apart so a
                                # real zero-token usage chunk still gets recorded.
                                has_usage = isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict)
                                if has_usage:
                                    input_tokens, output_tokens = get_llm_usage(chunk)
                                    infer_attrs["input_tokens"] = input_tokens
                                    infer_attrs["output_tokens"] = output_tokens
                                    set_llm_usage_input_tokens(input_tokens)
                                    set_llm_usage_output_tokens(output_tokens)
                        yield line

        return "stream", 200, gen()

    async def proxy_multipart(
        self,
        path: str,
        *,
        files: Dict[str, Any],
        data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Any]:
        """
        Forward a ``multipart/form-data`` POST. Used by the /audio/*
        passthrough routes — kept separate from ``proxy()`` so the JSON
        path stays 1:1 unchanged.

        ``files`` is the ``{field_name: (filename, bytes, content_type)}``
        dict that ``httpx.AsyncClient.post`` expects. ``data`` carries the
        non-file form fields (e.g. ``model``, ``language``, …).

        Same URL resolution as ``proxy()``: the upstream base comes from
        ``LLM_MODEL_ENDPOINTS[data['model']]`` or ``LLM_DEFAULT_ENDPOINT``.

        Failure modes are mapped to the OpenAI error envelope so callers
        can forward 4xx/5xx bodies unchanged:
          - misconfiguration (no endpoint set) -> 503
          - upstream network/transport error    -> 502
        Any 4xx/5xx the upstream itself returns is passed through; we trust
        upstream to be OpenAI-spec conformant for these audio routes.
        """
        data = dict(data or {})
        service_id = data.pop("serviceId", "") or ""
        model = data.get("model")

        with traced_span("model") as model_attrs:
            model_attrs["task_type"] = "LLM"
            model_attrs["model_name"] = model or "unknown"
            model_attrs["model_version"] = "unknown"
            model_attrs.update(get_context_attributes())
            model_attrs["service_id"] = service_id

            try:
                url = self.resolve_upstream_url(model=model, path=path)
            except ValueError as exc:
                logger.error("LLM proxy misconfiguration: %s", exc)
                return 503, {
                    "error": {"message": str(exc), "type": "api_error"}
                }

            logger.info("LLM proxy (multipart) -> %s (model=%s)", url, model)
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, files=files, data=data)
            except httpx.RequestError as exc:
                logger.warning(
                    "LLM upstream request failed (path=%s): %s", path, exc
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
