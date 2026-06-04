"""
Orchestrator for routing inference requests to appropriate TaskServices.
Handles task routing, service resolution, and request/model span tracing.
"""

import time
from typing import Any, Dict, Optional
from fastapi import Request
import logging

from opentelemetry import context as otel_context
from trace.request_span import (
    tracer,
    get_context_attributes,
    get_endpoint_path,
    compute_total_time_ms,
    finalize_span,
)

from services.base.task_service import BaseTaskService
from inference.inference_server_resolver import InferenceServerResolver
from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY


logger = logging.getLogger(__name__)

# Allowed task types — kept here (not derived from the registry) because SMR
# routes without a registry entry of its own.
ALLOWED_TASK_TYPES = [
    "NMT", "ASR", "OCR", "NER", "TTS", "PII", "LANGUAGE_DETECTION",
    "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION",
    "AUDIO_LANGUAGE_DETECTION", "SMR",
]


class Orchestrator:
    """
    Orchestrator manages the routing and execution of inference requests.
    Coordinates between generic request envelopes and task-specific services.

    Errors propagate with their original types (`raise ... from`) — the route
    layer maps the exception cause chain to client-safe HTTP statuses, so no
    orchestrator-specific exception wrappers are needed.
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.logger = logger
        self.inference_server_resolver = InferenceServerResolver()
        self.task_service_registry: dict = TASK_SERVICE_REGISTRY

    async def route_inference(
        self,
        payload: Dict[str, Any],
        request: Optional[Request] = None,
    ) -> Dict[str, Any]:
        """
        Route inference request to appropriate TaskService.
        Extracts task_type and delegates to task-specific service for processing.

        Args:
            payload: Raw request payload dictionary
            request: Optional FastAPI Request object for reading path and method

        Returns:
            Serialized response dictionary

        Raises:
            ValueError: If task_type is not registered
            RuntimeError: If service resolution or inference fails
        """
        # Start root span with parentID=null (empty context)
        start_time = time.time()
        ctx_attrs = get_context_attributes()
        end_point = str(request.url.path) if request else get_endpoint_path()
        request_method = request.method if request else ""

        with tracer.start_as_current_span(
            "request",
            context=otel_context.Context(),  # ensures parentID=null
        ) as request_span:
            try:
                task_type = payload.get("task_type", "").upper()
                self._validate_task_type(task_type)

                # Resolve service and model BEFORE creating task service
                service_info = await self._resolve_service_and_model(payload)

                # Instantiate and run the task service with the raw payload
                task_service = self._get_task_service(service_info)
                task_response = await task_service.process(payload, service_info)

                result = task_response.dict() if hasattr(task_response, 'dict') else task_response

                finalize_span(request_span, "request", {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "url": end_point,
                    "method": request_method,
                    "status": "success",
                    "status_code": 200,
                    **ctx_attrs,
                }, ok=True)
                return result  # type: ignore

            except Exception as e:
                finalize_span(request_span, "request", {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "url": end_point,
                    "method": request_method,
                    "status": "failure",
                    # ValueError = bad request input, not a server-side failure
                    "status_code": 400 if isinstance(e, ValueError) else 500,
                    **ctx_attrs,
                }, error=e)
                raise

    def _validate_task_type(self, task_type: str) -> None:
        """Raise ValueError if task_type is not a known task."""
        if task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(
                f"Unknown task_type: {task_type}. Allowed: {', '.join(ALLOWED_TASK_TYPES)}"
            )

    def _get_task_service(self, service_info: Dict[str, Any]) -> BaseTaskService:
        """
        Instantiate the task service for the resolved service_info.
        Looks up TASK_SERVICE_REGISTRY by mm_models.class_instance.

        Raises:
            RuntimeError: If class_instance is unset or unknown (platform/config
                          gap, not a client error)
        """
        # class_instance comes from mm_models.class_instance via the resolver —
        # adding a model in the platform needs no code change here.
        class_instance = service_info.get("class_instance")
        if not class_instance:
            raise RuntimeError(
                f"No class_instance set on model for serviceId='"
                f"{service_info.get('name', '')}'. "
                f"Set the classInstance field on the model in the platform."
            )

        service_class = self.task_service_registry.get(class_instance)
        if not service_class:
            raise RuntimeError(
                f"Unknown class_instance '{class_instance}'. "
                f"Register it in task_service_registry.py."
            )

        self.logger.debug(
            f"Instantiating {class_instance} for serviceId='{service_info.get('name', '')}'"
        )
        return service_class(service_info=service_info)  # type: ignore

    async def _resolve_service_and_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve the model service details from the raw request payload.
        Extracted here so the Orchestrator can route to the correct model-specific
        TaskService class before instantiation, rather than always mapping task_type
        to a single fixed service.

        Args:
            payload: Raw request payload dictionary (must contain config.serviceId
                     or a top-level serviceId field)

        Returns:
            Dict with keys: serviceId, name, endpoint, api_key, adapter_config, ...

        Raises:
            RuntimeError: If the service cannot be resolved
        """
        start_time = time.time()
        ctx_attrs = get_context_attributes()
        task_type = payload.get("task_type", "").upper()

        with tracer.start_as_current_span("model") as model_span:
            # Extract serviceId: check config block first, then top-level
            config_block = payload.get("config", {})
            if isinstance(config_block, dict):
                serviceId = config_block.get("serviceId") or payload.get("serviceId")
            else:
                serviceId = getattr(config_block, "serviceId", None) or payload.get("serviceId")

            if not serviceId:
                # Fall back to SMR or a safe default
                serviceId = await self.inference_server_resolver.resolve_smr_service(payload)
                self.logger.warning(
                    f"No serviceId in payload, SMR resolved to: {serviceId}"
                )

            self.logger.debug(f"Resolving service: {serviceId}")
            try:
                service_info = await self.inference_server_resolver.resolve_service(serviceId)

                adapter_cfg = service_info.get("adapter_config") or {}
                finalize_span(model_span, "model", {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "model_name": service_info.get("name", ""),
                    "model_version": service_info.get("model_version") or adapter_cfg.get("model_version", "unknown"),
                    "task_type": task_type,
                    **ctx_attrs,
                }, ok=True)
                return service_info
            except Exception as e:
                finalize_span(model_span, "model", {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "task_type": task_type,
                    **ctx_attrs,
                }, error=e)
                self.logger.error(
                    f"Failed to resolve service '{serviceId}': {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Orchestrator: Failed to resolve service '{serviceId}': {e}"
                ) from e
