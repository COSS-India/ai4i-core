"""
Task service interface and base class defining the contract for all inference task services.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ITaskService(ABC):
    """
    Interface that all task services must implement.
    Defines the contract for inference pipeline execution.
    """

    @abstractmethod
    async def validate_request(self, request: BaseModel) -> None:
        """
        Validate the incoming request.

        Args:
            request: Task-specific request model

        Raises:
            ValueError: If request is invalid
        """
        pass

    @abstractmethod
    async def preprocess_input(self, input_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess input data before inference.
        Handles task-specific transformations like text normalization, audio resampling, etc.

        Args:
            input_data: List of input dictionaries from request

        Returns:
            Preprocessed input data ready for inference
        """
        pass

    @abstractmethod
    async def run_inference(
        self,
        request: BaseModel,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> BaseModel:
        """
        Execute the core inference logic.
        Called by process() after validation and preprocessing.
        Subclasses implement the actual Triton inference call here.

        Args:
            request: Task-specific request model
            user_id: Optional user ID for tracking
            api_key_id: Optional API key ID for tracking
            session_id: Optional session ID for tracing

        Returns:
            Task-specific response model
        """
        pass

    @abstractmethod
    async def postprocess_output(
        self, raw_triton_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post-process raw Triton inference output.
        Handles task-specific transformations like decoding, formatting, etc.

        Args:
            raw_triton_output: Raw output dictionary from Triton server

        Returns:
            Formatted output dictionary for response
        """
        pass


class BaseTaskService(ITaskService):
    """
    Abstract base class providing common functionality for all task services.
    Implements Template Method pattern for the inference pipeline.
    
    Subclasses must implement run_inference() with actual inference logic.
    Subclasses may override validate_request(), preprocess_input(), postprocess_output() as needed.
    """

    def __init__(self):
        """
        Initialize base task service.
        Automatically creates InferenceServerResolver instance for all subclasses.
        """
        from inference.inference_server_resolver import InferenceServerResolver
        
        self.task_name = self.__class__.__name__
        self.inference_server_resolver = InferenceServerResolver()

    async def process(
        self,
        payload: Dict[str, Any],
    ) -> BaseModel:
        """
        Execute the complete inference pipeline (Template Method).
        Deserializes payload → validate → preprocess → run_inference → postprocess.
        
        This is the main entry point - Orchestrator calls this method with raw payload.
        Subclasses override _deserialize_payload() and other methods as needed.

        Args:
            payload: Raw request payload dictionary

        Returns:
            Task-specific response model

        Raises:
            ValueError: If validation fails
        """
        # 0. Deserialize payload to task-specific request (implemented by subclass)
        request = await self._deserialize_payload(payload)
        
        # 1. Validate request
        await self.validate_request(request)

        # 2. Preprocess input - extract and preprocess based on input type
        input_data = (
            getattr(request, 'input', None)
            or getattr(request, 'audio', None)
            or getattr(request, 'image', None)
        )
        if input_data:
            preprocessed_input = await self.preprocess_input(input_data)
            # Update request with preprocessed input
            for attr_name in ('input', 'audio', 'image'):
                if getattr(request, attr_name, None) is not None:
                    setattr(request, attr_name, preprocessed_input)
                    break

        # 3. Run inference (implemented by subclass)
        response = await self.run_inference(request)

        return response

    @abstractmethod
    async def _deserialize_payload(self, payload: Dict[str, Any]) -> BaseModel:
        """
        Deserialize raw payload dictionary to task-specific request model.
        Each task service implements this for its specific payload format.

        Args:
            payload: Raw request payload dictionary

        Returns:
            Task-specific deserialized request model
        """
        pass

    async def validate_request(self, request: BaseModel) -> None:
        """
        Validate the incoming request.
        Override in subclasses for task-specific validation.

        Args:
            request: Task-specific request model

        Raises:
            ValueError: If request is invalid
        """
        if request is None:
            raise ValueError(f"{self.task_name}: Request cannot be None")

    async def preprocess_input(self, input_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Preprocess input data before inference.
        Override in subclasses for task-specific transformations like text normalization, audio resampling, etc.

        Args:
            input_data: List of input dictionaries from request

        Returns:
            Preprocessed input data ready for inference
        """
        if not input_data:
            raise ValueError(f"{self.task_name}: Input data cannot be empty")
        return input_data

    @abstractmethod
    async def run_inference(
        self,
        request: BaseModel
    ) -> BaseModel:
        """
        Execute the core inference logic.
        Subclasses must implement this with actual inference logic:
        - Resolve service/model via InferenceServerResolver
        - Create InferenceModel converter
        - Convert payload to Triton format
        - Call Triton inference server
        - Convert Triton output back to task format
        - Return response

        Args:
            request: Task-specific request model            user_id: Optional user ID for tracking
            api_key_id: Optional API key ID for tracking
            session_id: Optional session ID for tracing

        Returns:
            Task-specific response model
        """
        pass

    async def postprocess_output(
        self, raw_triton_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post-process raw Triton inference output.
        Override in subclasses for task-specific transformations like decoding, formatting, etc.

        Args:
            raw_triton_output: Raw output dictionary from Triton server

        Returns:
            Formatted output dictionary for response
        """
        if not raw_triton_output:
            raise ValueError(f"{self.task_name}: Raw output cannot be empty")
        return raw_triton_output
