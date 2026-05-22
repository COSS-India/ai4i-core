"""
Orchestrator for routing inference requests to appropriate TaskServices.
Handles polymorphic payload deserialization, validation, and response serialization.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, ValidationError
import logging

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
        self.task_service_registry: list = TASK_SERVICE_REGISTRY

    async def route_inference(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Route inference request to appropriate TaskService.
        Extracts task_type and delegates to task-specific service for processing.

        Args:
            payload: Raw request payload dictionary

        Returns:
            Serialized response dictionary

        Raises:
            UnknownTaskTypeError: If task_type not registered
            TaskServiceExecutionError: If task service execution fails
        """
        try:
            # Extract task type from payload
            task_type = payload.get("task_type", "").upper()
            self.logger.info(f"Routing {task_type} inference request...")
            
            # Validate task type
            await self._validate_task_type(task_type)

            # Resolve service and model BEFORE creating task service
            # so the correct model-specific class can be instantiated
            service_info = await self._resolve_service_and_model(payload)

            # Get task service for this task type, injecting resolved service info
            task_service = await self._get_task_service(task_type, service_info)
            
            # Execute task service with raw payload
            # Task service handles its own payload deserialization
            task_response = await self._execute_task_service(
                task_service=task_service,
                payload=payload,
            )
            
            # Serialize response
            return task_response.dict() if hasattr(task_response, 'dict') else task_response
            
        except OrchestratorError:
            raise
        except Exception as e:
            raise TaskServiceExecutionError(f"Orchestration failed: {str(e)}")

    async def _validate_task_type(self, task_type: str) -> None:
        """
        Validate that task_type is registered.

        Args:
            task_type: Task type to validate

        Raises:
            UnknownTaskTypeError: If task_type not registered
        """
        # For now, allow all known task types
        allowed_tasks = ["NMT", "ASR", "OCR", "NER", "LLM", "TTS", "PII", "LANGUAGE_DETECTION", "SPEAKER_DIARIZATION", "TRANSLITERATION", "AUDIO_LANG_DETECTION", "SMR"]
        if task_type not in allowed_tasks:
            raise UnknownTaskTypeError(f"Unknown task_type: {task_type}. Allowed: {', '.join(allowed_tasks)}")



    async def _get_task_service(
        self, task_type: str, service_info: Dict[str, Any]
    ) -> ITaskService:
        """
        Get or instantiate task service for given task_type and resolved service_info.
        Delegates to TaskFactory for service instantiation.

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

            # Search flat list: find entry where task_type matches
            # AND serviceId is listed in the model_name array
            registry_entry = next(
                (
                    entry for entry in self.task_service_registry
                    if entry.get("task_type") == task_type
                    and serviceId in entry.get("model_name", [])
                ),
                None,
            )

            if not registry_entry:
                raise TaskServiceExecutionError(
                    f"No registry entry found for task_type='{task_type}', "
                    f"serviceId='{serviceId}'. "
                    f"Add it to task_service_registry.json under the matching "
                    f"task_type entry's model_name list."
                )

            service_class = registry_entry.get("service_class")
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
        self, payload: Dict[str, Any]
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
            self.logger.info(
                f"Resolved serviceId='{serviceId}' → "
                f"model='{service_info.get('name')}', "
                f"endpoint='{service_info.get('endpoint')}'"
            )
            return service_info
        except Exception as e:
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
            result = await task_service.process(payload)  # type: ignore
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
