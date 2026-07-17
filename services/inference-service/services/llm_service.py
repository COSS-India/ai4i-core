"""OpenAI-compatible LLM proxy service."""

import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from config import settings
from inference.inference_server_resolver import InferenceServerResolver
from trace.request_span import traced_span, traced_inference, get_context_attributes


logger = logging.getLogger(__name__)

# Module-level singleton — mirrors the Orchestrator pattern so the TTL cache
# is shared across requests rather than rebuilt on every /chat call.
_resolver = InferenceServerResolver()


class OpenAIProxyService:
    """
    Thin proxy to an OpenAI-compatible upstream LLM server.

    Resolves the upstream base URL from MMS using serviceId (same lookup used
    by Triton-backed services), appends the OpenAI-compatible path, and
    forwards the JSON payload.
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

    async def proxy_traced(
        self,
        path: str,
        payload: Any,
        request: Optional[Any] = None,
    ) -> Tuple[int, Any]:
        """
        Full LLM proxy with MMS resolution, tier gate, and OTel spans.

        Order matches the Orchestrator + BaseTaskService pattern:
          1. Extract serviceId from payload
          2. Resolve endpoint + service_info from MMS (cached)
          3. Tier entitlement check — before creating billing spans
          4. Inject model name into payload for upstream vLLM
          5. Emit model + ai-inference spans wrapping the actual forward
        """
        # Strip serviceId before forwarding — upstream doesn't accept it.
        if isinstance(payload, dict):
            config_block = payload.get("config") or {}
            service_id = (
                config_block.get("serviceId") if isinstance(config_block, dict) else None
            ) or payload.get("serviceId", "") or ""
            payload = {k: v for k, v in payload.items() if k != "serviceId"}
        else:
            service_id = ""

        # Resolve service from MMS (result is TTL-cached).
        try:
            url, service_info = await self.resolve_upstream_url(service_id=service_id, path=path)
        except LookupError:
            logger.error("LLM service not found: %s", service_id)
            return 404, {"detail": f"Service '{service_id}' not found"}
        except (ConnectionError, ValueError):
            logger.error("LLM proxy unavailable for service: %s", service_id)
            return 503, {"detail": "LLM service unavailable"}

        # Tier entitlement check — mirrors orchestrator.py for Triton services.
        # Runs before creating billing spans so a 403 produces no ai-inference span.
        if request is not None:
            tier_id = request.headers.get("X-Tier-ID", "")
            if tier_id:
                allowed_tiers = [str(t) for t in service_info.get("tier_ids", [])]
                if tier_id not in allowed_tiers:
                    return 403, {"detail": f"Service '{service_id}' is not available for your quota"}

        # Inject model name from MMS adapter_config so upstream vLLM receives
        # the model field it expects — clients send serviceId, not model.
        model_name = (service_info.get("adapter_config") or {}).get("model_name", "") if isinstance(payload, dict) else ""
        if model_name and isinstance(payload, dict):
            payload = {**payload, "model": model_name}

        with traced_span("model") as model_attrs:
            model_attrs["task_type"] = "LLM"
            model_attrs["model_name"] = model_name or "unknown"
            model_attrs["model_version"] = "unknown"
            model_attrs.update(get_context_attributes())
            model_attrs["service_id"] = service_id

            async with traced_inference(payload, "LLM", logger) as infer_attrs:
                # service_id and tenantId must be set explicitly: the PPU Kafka
                # consumer reads only the ai-inference span for billing.
                infer_attrs["service_id"] = service_id
                infer_attrs["tenantId"] = model_attrs.get("tenantId", "")

                logger.info("LLM proxy -> %s (service_id=%s)", url, service_id)
                try:
                    status_code, body = await self.forward(url, payload)
                except httpx.RequestError as exc:
                    logger.warning("LLM upstream request failed (path=%s): %s", path, exc)
                    return 502, {"detail": "Upstream LLM request failed"}

                if status_code >= 400 and isinstance(body, dict):
                    message = (
                        body.get("detail")
                        or (body.get("error") or {}).get("message")
                        or body.get("message")
                        or "Upstream LLM error"
                    )
                    body = {"detail": message}

                if isinstance(body, dict):
                    usage = body.get("usage") or {}
                    infer_attrs["input_tokens"] = usage.get("prompt_tokens", 0)
                    infer_attrs["output_tokens"] = usage.get("completion_tokens", 0)
                    infer_attrs["output_type"] = "text"
                    # vLLM echoes the model name in the response — capture it for
                    # the model span now that clients no longer send it in the request.
                    model_attrs["model_name"] = body.get("model", "unknown")

        return status_code, body

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

        Endpoint resolution uses MMS via serviceId (same as JSON routes).
        model name is injected from adapter_config before forwarding.
        """
        data = dict(data or {})
        service_id = data.pop("serviceId", "") or ""

        # Resolve service from MMS (result is TTL-cached).
        try:
            url, service_info = await self.resolve_upstream_url(service_id=service_id, path=path)
        except LookupError:
            logger.error("LLM audio service not found: %s", service_id)
            return 404, {"error": {"message": f"Service '{service_id}' not found", "type": "not_found"}}
        except (ConnectionError, ValueError):
            logger.error("LLM audio proxy unavailable for service: %s", service_id)
            return 503, {"error": {"message": "Service unavailable", "type": "api_error"}}

        # Tier entitlement check.
        if request is not None:
            tier_id = request.headers.get("X-Tier-ID", "")
            if tier_id:
                allowed_tiers = [str(t) for t in service_info.get("tier_ids", [])]
                if tier_id not in allowed_tiers:
                    return 403, {"error": {
                        "message": f"Service '{service_id}' is not available for your quota",
                        "type": "permission_error",
                    }}

        # Inject model name from MMS adapter_config.
        model_name = (service_info.get("adapter_config") or {}).get("model_name", "")
        if model_name:
            data["model"] = model_name
        model = data.get("model", "")

        with traced_span("model") as model_attrs:
            model_attrs["task_type"] = "LLM"
            model_attrs["model_name"] = model or "unknown"
            model_attrs["model_version"] = "unknown"
            model_attrs.update(get_context_attributes())
            model_attrs["service_id"] = service_id

        logger.info("LLM proxy (multipart) -> %s (service_id=%s)", url, service_id)
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
