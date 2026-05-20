"""
TaskFactory for instantiating task-specific services based on task_type.
Manages service registration and dependency injection.
"""

from typing import Any, Dict, Optional
import logging

from models.task_types import task_registry, TaskType
from interfaces.task_service import ITaskService


logger = logging.getLogger(__name__)


class FactoryError(Exception):
    """Base exception for factory errors."""

    pass


class ServiceInstantiationError(FactoryError):
    """Raised when service instantiation fails."""

    pass


class TaskFactory:
    """
    Factory for creating TaskService instances based on task_type.
    Manages service registration, dependency injection, and lifecycle.
    """

    def __init__(self):
        """Initialize task factory."""
        self.task_registry = task_registry
        self.logger = logger
        self._service_cache: Dict[str, ITaskService] = {}

    async def create_service(
        self,
        task_type: str,
        **dependencies: Any,
    ) -> ITaskService:
        """
        Create and return TaskService instance for given task_type.
        Caches services to avoid repeated instantiation.

        Args:
            task_type: Type of service to create
            **dependencies: Dependencies to inject into service
                (redis_client, model_management_client, triton_client_factory, etc.)

        Returns:
            TaskService instance ready for use

        Raises:
            ServiceInstantiationError: If service creation fails
        """
        try:
            # Check cache first
            if task_type in self._service_cache:
                return self._service_cache[task_type]
            
            # For NMT service
            if task_type == "NMT":
                try:
                    from services.nmt_service import NMTTaskService
                    from inference.inference_server_resolver import InferenceServerResolver
                    
                    # Create resolver instance
                    resolver = InferenceServerResolver()
                    service = NMTTaskService(inference_server_resolver=resolver)  # type: ignore
                    self._service_cache[task_type] = service  # type: ignore
                    return service  # type: ignore
                except ImportError:
                    logger.warning(f"NMTTaskService not found, using mock")
            
            # For other tasks, create mock
            logger.warning(f"No implementation for {task_type}, returning mock service")
            
            # Create inline mock service
            class InlineMockService:  # type: ignore
                async def process(self, request, user_id=None, api_key_id=None, session_id=None):
                    return {"output": [], "status": "mock"}
            
            service = InlineMockService()  # type: ignore
            self._service_cache[task_type] = service  # type: ignore
            return service  # type: ignore
            
        except Exception as e:
            raise ServiceInstantiationError(f"Failed to create {task_type} service: {str(e)}")
