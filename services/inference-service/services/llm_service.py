"""OpenAI-compatible LLM proxy service."""

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from config import settings
from trace.request_span import traced_span, traced_inference, get_context_attributes


logger = logging.getLogger(__name__)


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

    async def proxy_traced(
        self,
        path: str,
        payload: Any,
        request=None,
    ) -> Tuple[int, Any]:
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

        with traced_span("model") as model_attrs:
            model_attrs["task_type"] = "LLM"
            model_attrs["model_name"] = payload.get("model", "unknown") if isinstance(payload, dict) else "unknown"
            model_attrs["model_version"] = "unknown"
            model_attrs.update(get_context_attributes())
            model_attrs["service_id"] = service_id

            async with traced_inference(payload, "LLM", logger, request=request) as infer_attrs:
                # service_id is not in context vars — must be copied explicitly.
                # tenantId is also set explicitly: the PPU Kafka consumer reads only
                # the ai-inference span for billing, so it must always be present
                # even if the contextvar is None (get_context_attributes skips None).
                infer_attrs["service_id"] = service_id
                infer_attrs["tenantId"] = model_attrs.get("tenantId", "")

                status_code, body = await self.proxy(path=path, payload=payload)

                if isinstance(body, dict):
                    usage = body.get("usage") or {}
                    infer_attrs["input_tokens"] = usage.get("prompt_tokens", 0)
                    infer_attrs["output_tokens"] = usage.get("completion_tokens", 0)
                    infer_attrs["output_type"] = "text"

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
