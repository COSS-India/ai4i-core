"""
Orchestrator for routing inference requests to appropriate TaskServices.
Handles polymorphic payload deserialization, validation, and response serialization.
"""

import time
from typing import Any, Dict, Optional
from fastapi import Request
from pydantic import BaseModel, ValidationError
import logging

from opentelemetry import trace, context as otel_context
from opentelemetry.trace import StatusCode
from trace.request_span import tracer, get_context_attributes, get_endpoint_path, compute_total_time_ms, log_span_attributes

from models.common import GenericInferenceRequest, GenericInferenceResponse
from models.task_types import task_registry
from interfaces.task_service import ITaskService
from inference.inference_server_resolver import InferenceServerResolver
from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY


logger = logging.getLogger(__name__)


class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""

    pass


class UnknownTaskTypeError(OrchestratorError):
    """Raised when task_type is not registered."""

    pass


class PayloadValidationError(OrchestratorError):
    """Raised when payload validation fails."""

    pass


class TaskServiceExecutionError(OrchestratorError):
    """Raised when task service execution fails."""

    pass


class Orchestrator:
    """
    Orchestrator manages the routing and execution of inference requests.
    Coordinates between generic request envelopes and task-specific services.
    """

    def __init__(self):
        """Initialize orchestrator."""
        self.task_registry = task_registry
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
            UnknownTaskTypeError: If task_type not registered
            TaskServiceExecutionError: If task service execution fails
        """
        # Start root span with parentID=null (empty context)
        start_time = time.time()
        ctx_attrs = get_context_attributes(request)
        end_point = str(request.url.path) if request else get_endpoint_path()
        request_method = request.method if request else ""

        with tracer.start_as_current_span(
            "request",
            context=otel_context.Context(),  # ensures parentID=null
        ) as request_span:
            try:
                # Extract task type from payload
                task_type = payload.get("task_type", "").upper()

                # Validate task type
                await self._validate_task_type(task_type)

                # Resolve service and model BEFORE creating task service
                service_info = await self._resolve_service_and_model(payload, request=request)

                # Get task service for this task type, injecting resolved service info
                task_service = await self._get_task_service(task_type, service_info)

                # Execute task service with raw payload
                task_response = await self._execute_task_service(
                    task_service=task_service,
                    payload=payload,
                    serviceInfo=service_info,
                )

                # Serialize response
                result = task_response.dict() if hasattr(task_response, 'dict') else task_response

                # Set root span attributes on success
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "url": end_point,
                    "method": request_method,
                    "status": "success",
                    "status_code": 200,
                    **ctx_attrs,
                }
                for k, v in span_attrs.items():
                    request_span.set_attribute(k, v)
                request_span.set_status(StatusCode.OK)
                log_span_attributes("request", request_span, span_attrs)

                return result # type: ignore

            except OrchestratorError as e:
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "end_point": end_point,
                    "request_method": request_method,
                    "status": "failure",
                    "status_code": 500,
                    **ctx_attrs,
                }
                for k, v in span_attrs.items():
                    request_span.set_attribute(k, v)
                request_span.set_status(StatusCode.ERROR, str(e))
                log_span_attributes("request", request_span, span_attrs)

                raise TaskServiceExecutionError(f"Orchestration failed: {str(e)}")

    async def _validate_task_type(self, task_type: str) -> None:
        """
        Validate that task_type is registered.

        Args:
            task_type: Task type to validate

        Raises:
            UnknownTaskTypeError: If task_type not registered
        """
        # Allowed tasks are exactly the ones with a registered TaskService class.
        if task_type not in self.task_service_registry:
            allowed = ", ".join(self.task_service_registry)
            raise UnknownTaskTypeError(f"Unknown task_type: {task_type}. Allowed: {allowed}")



    async def _get_task_service(
        self, task_type: str, service_info: Dict[str, Any]
    ) -> ITaskService:
        """
        Get or instantiate task service for given task_type and resolved service_info.
        Looks up TASK_SERVICE_REGISTRY and instantiates the matching service class.

        Args:
            task_type: Task type to get service for
            service_info: Resolved service information from _resolve_service_and_model
                          (includes endpoint, model name, adapter_config, etc.)

        Returns:
            TaskService instance ready for execution, initialized with service_info

        Raises:
            TaskServiceExecutionError: If service instantiation fails
        """
        try:
            # serviceId (model name) comes from the resolved service_info
            serviceId = service_info.get("name", "") or service_info.get("serviceId", "")

            # Which model serves the request was already resolved against MMS;
            # the registry only maps task_type to the TaskService class.
            service_class = self.task_service_registry.get(task_type)

            if not service_class:
                raise TaskServiceExecutionError(
                    f"No registry entry found for task_type='{task_type}'. "
                    f"Add it to TASK_SERVICE_REGISTRY in "
                    f"orchestrator/task_service_registry.py."
                )

            self.logger.debug(
                f"Instantiating {service_class.__name__} "
                f"for task_type='{task_type}', serviceId='{serviceId}'"
            )
            return service_class(service_info=service_info)  # type: ignore
        except TaskServiceExecutionError:
            raise
        except Exception as e:
            raise TaskServiceExecutionError(f"Failed to get task service: {str(e)}")

    async def _resolve_service_and_model(
        self, payload: Dict[str, Any], request: Optional[Request] = None
    ) -> Dict[str, Any]:
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
        ctx_attrs = get_context_attributes(request)
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

                # Set model span attributes
                adapter_cfg = service_info.get("adapter_config") or {}
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "model_name": service_info.get("name", ""),
                    "model_version": service_info.get("model_version") or adapter_cfg.get("model_version", "unknown"),
                    "task_type": task_type,
                    **ctx_attrs,
                }
                for k, v in span_attrs.items():
                    model_span.set_attribute(k, v)
                model_span.set_status(StatusCode.OK)
                log_span_attributes("model", model_span, span_attrs)

                return service_info
            except Exception as e:
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "task_type": task_type,
                    **ctx_attrs,
                }
                for k, v in span_attrs.items():
                    model_span.set_attribute(k, v)
                model_span.set_status(StatusCode.ERROR, str(e))
                log_span_attributes("model", model_span, span_attrs)
                self.logger.error(
                    f"Failed to resolve service '{serviceId}': {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Orchestrator: Failed to resolve service '{serviceId}': {e}"
                ) from e

    async def _execute_task_service(
        self,
        task_service: ITaskService,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> BaseModel:
        """
        Execute task service with raw payload.
        Task service is responsible for deserializing the payload.

        Args:
            task_service: TaskService instance to execute
            payload: Raw request payload dictionary

        Returns:
            Task-specific response model

        Raises:
            TaskServiceExecutionError: If service execution fails
        """
        try:
            result = await task_service.process(payload, serviceInfo)  # type: ignore
            return result  # type: ignore
        except Exception as e:
            raise TaskServiceExecutionError(f"Task service execution failed: {str(e)}")

    async def _serialize_response(
        self, task_type: str, response: BaseModel
    ) -> Dict[str, Any]:
        """
        Serialize task-specific response to dictionary.
        Uses correct response model for task type.

        Args:
            task_type: Task type to use for serialization
            response: Task-specific response model instance

        Returns:
            Serialized response dictionary

        Raises:
            PayloadValidationError: If serialization fails
        """
        try:
            if isinstance(response, dict):
                return response
            return response.dict()  # type: ignore
        except Exception as e:
            raise PayloadValidationError(f"Response serialization failed: {str(e)}")

    def _log_request_start(
        self,
    ) -> None:
        """
        Log start of inference request.

        Args:
            task_type: Task type being processed
            user_id: Optional user ID
            session_id: Optional session ID
        """
        pass

    def _log_request_complete(
        self,
        task_type: str,
        success: bool,
        error_msg: Optional[str] = None,
    ) -> None:
        """
        Log completion of inference request.

        Args:
            task_type: Task type that was processed
            session_id: Optional session ID
            success: Whether request succeeded
            error_msg: Optional error message if failed
        """
        pass
