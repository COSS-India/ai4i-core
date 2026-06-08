"""OpenAI-compatible LLM proxy service."""

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from config import settings


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
        model = (data or {}).get("model")
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
                response = await client.post(url, files=files, data=data or {})
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
