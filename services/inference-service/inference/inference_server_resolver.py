"""
InferenceServerResolver — looks up Triton endpoints and adapter config from the
model management service, with a TTL'd in-memory cache.
"""

from typing import Any, Dict, Tuple
import logging
import time

from config import settings

from utils import HTTPServiceClient


logger = logging.getLogger(__name__)


class InferenceServerResolver:
    """
    Resolver for finding Triton inference endpoints and model information.

    Caches resolved services in memory for CACHE_TTL_SECONDS so MMS updates
    (e.g. adapter_config changes) propagate without a restart, while repeat
    requests within the TTL skip the MMS round-trip entirely.
    """

    def __init__(self):
        # service_id -> (service_info, cached_at)
        self._memory_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}

    async def resolve_service(self, service_id: str) -> Dict[str, Any]:
        """
        Resolve inference service information (name, endpoint, api_key,
        adapter_config) for the given service_id, via cache or MMS.

        Raises:
            LookupError: If the service does not exist in MMS
            ConnectionError: If MMS is unreachable/unhealthy
        """
        # resolve_ms is timed one level up (Orchestrator) so it matches the
        # model span scope. Here we only record cache_hit and time the MMS
        # round-trip (mms_http_ms, inside _query_model_management_service).
        from trace.phase_timer import record_attr

        cached = self._memory_cache.get(service_id)
        if cached and time.time() - cached[1] < settings.CACHE_TTL_SECONDS:
            logger.debug(f"Cache hit for service {service_id}")
            record_attr("cache_hit", True)
            return cached[0]

        record_attr("cache_hit", False)
        service_info = await self._query_model_management_service(service_id)
        self._memory_cache[service_id] = (service_info, time.time())
        return service_info

    async def resolve_smr_service(self, payload: Dict[str, Any]) -> str:
        """
        Resolve service_id via SmartModelRouter when not explicitly provided.

        SMR is not implemented — requests must carry config.serviceId (or a
        top-level serviceId). Raising here surfaces a clear 400 instead of
        silently routing every serviceId-less request to a default model.
        """
        raise ValueError(
            "serviceId is required (config.serviceId or top-level serviceId); "
            "SmartModelRouter routing is not implemented"
        )

    async def _query_model_management_service(self, service_id: str) -> Dict[str, Any]:
        """
        Fetch service details from the model management service.

        Raises:
            LookupError: If the service is not found (404)
            ConnectionError: On transport/availability failures
        """
        model_management_url = settings.MODEL_MANAGEMENT_SERVICE_URL
        if not model_management_url:
            logger.error("MODEL_MANAGEMENT_SERVICE_URL not configured")
            raise RuntimeError("Model management service not configured")

        from trace.phase_timer import timed_phase

        try:
            http_client = HTTPServiceClient(timeout=settings.MODEL_MANAGEMENT_SERVICE_TIMEOUT)
            url = f"{model_management_url.rstrip('/')}/api/v1/services/{service_id}"
            async with timed_phase("mms_http_ms"):
                raw = await http_client.get_json(url)
            service_info = self._normalize_mms_response(raw, service_id)
            # Never log the full service_info dict — it contains the resolved
            # Triton endpoint URL and api_key. Log only the safe identifiers
            # so we can correlate without exposing internal infra to anyone
            # who can read inference-service logs (incl. via Logs Dashboard).
            logger.debug(
                "Resolved service id=%s name=%s",
                service_id, service_info.get("name", ""),
            )
            return service_info

        except LookupError as e:
            # Don't include str(e) — upstream HTTP error reprs frequently
            # embed the MMS URL or the resolved Triton URL.
            logger.error("Service %s not found", service_id)
            raise LookupError(f"Service {service_id} not found") from e
        except ConnectionError:
            raise
        except Exception as e:
            # Transport/availability failure is NOT "service not found" — a
            # hung or unreachable MMS must surface as a 502-class dependency
            # error, not a 404 (and not pollute logs with "not found").
            # Log only the exception TYPE — str(e) on httpx/urllib3 errors
            # typically embeds the full URL.
            logger.error(
                "Model management service query failed for %s: %s",
                service_id, type(e).__name__,
            )
            raise ConnectionError(
                f"Model management service unavailable while resolving '{service_id}'"
            ) from e

    def _normalize_mms_response(self, raw: Dict[str, Any], service_id: str) -> Dict[str, Any]:
        """
        Normalize MMS response to internal service info format.

        Real MMS returns {"success": true, "data": {...camelCase...}} with base endpoint
        and inference path split across data.endpoint and data.model.inferenceEndPoint.schema.endpoint.
        Flat shape (no envelope) is passed through as-is for legacy/fallback.

        Returns:
            Normalized dict with keys: name, endpoint, api_key, adapter_config
        """
        # Real MMS shape: {"success": true, "data": {...}}
        if "success" in raw and "data" in raw:
            data = raw["data"]
            model_block = data.get("model") or {}
            inference_endpoint = model_block.get("inferenceEndPoint", {})
            schema = inference_endpoint.get("schema", {})

            base_endpoint = data.get("endpoint", "").rstrip("/")
            model_name = schema.get("model_name", "")
            endpoint = f"{base_endpoint}/v2/models/{model_name}/infer" if model_name else base_endpoint

            # adapter_config can be at data level or nested under inferenceEndPoint
            adapter_config = (
                data.get("adapter_config")
                or inference_endpoint.get("adapter_config")
                or inference_endpoint.get("adapterConfig")
            )
            if not adapter_config:
                logger.warning(
                    "Service %s: adapter_config missing from MMS response — "
                    "model class must supply a default or this request will fail.",
                    service_id,
                )
            submitter = model_block.get("submitter") or {}
            return {
                "name": data.get("serviceName") or data.get("name"),
                "endpoint": endpoint,
                "api_key": data.get("apiKey") or data.get("api_key"),
                "adapter_config": adapter_config,
                "class_instance": model_block.get("classInstance"),
                "is_published": bool(data.get("isPublished", False)),
                "tier_ids": data.get("tierIds") or [],
                # Model identity metadata — surfaced in the inference response
                # (models/common.py ModelMetadata) so clients can echo
                # modelProvider/modelVersion into the Feedback API.
                "model_id": model_block.get("modelId") or data.get("modelId"),
                "model_version": model_block.get("version") or data.get("modelVersion"),
                "model_provider": submitter.get("name") if isinstance(submitter, dict) else None,
                "language": model_block.get("languages") or [],
            }

        # Flat shape (legacy/fallback): pass through as-is, but ensure
        # is_published and tier_ids are always present so the orchestrator
        # gates are never skipped by a missing key.
        return {
            **raw,
            "is_published": bool(raw.get("is_published", False)),
            "tier_ids": raw.get("tier_ids", []),
        }
