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
    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Validate the incoming request payload.

        Args:
            payload: Raw request payload dictionary

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
        payload: Dict[str, Any],
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> BaseModel:
        """
        Execute the core inference logic.
        Called by process() after validation and preprocessing.
        Subclasses implement the actual Triton inference call here.

        Args:
            payload: Raw request payload dictionary
            user_id: Optional user ID for tracking
            api_key_id: Optional API key ID for tracking
            session_id: Optional session ID for tracing

        Returns:
            Task-specific response model
        """
        pass

    @abstractmethod
    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Post-process inference output into a response-ready dict.
        Text services pass source_texts via kwargs; audio/image services pass their own fields.

        Args:
            response_items: Output dicts from convert_triton_output_to_task_format
            **kwargs: Modality-specific context (e.g. source_texts for text)

        Returns:
            Formatted output dictionary for response
        """
        pass

    @abstractmethod
    def _build_response(self, payload: Any, postprocessed: Dict[str, Any]) -> Any:
        """Build typed response model from postprocessed inference output."""
        pass


class BaseTaskService(ITaskService):
    """
    Abstract base class providing common functionality for all task services.
    Implements Template Method pattern for the inference pipeline.

    Subclasses must implement run_inference() with actual inference logic.
    Subclasses may override validate_request(), preprocess_input(), postprocess_output() as needed.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None):
        """
        Initialize base task service.

        Args:
            service_info: Pre-resolved service dict injected by the Orchestrator/Factory
                          (contains endpoint, model name, adapter_config, api_key, etc.).
                          When provided, execute_triton_inference uses it directly
                          without a redundant resolver call.
        """
        import logging
        self.task_name = self.__class__.__name__
        self.service_info: Dict[str, Any] = service_info or {}
        self.logger = logging.getLogger(__name__)

    async def process(
        self,
        payload: Dict[str, Any],
    ) -> BaseModel:
        """
        Execute the complete inference pipeline (Template Method).
        validate → preprocess → run_inference.

        This is the main entry point - Orchestrator calls this method with raw payload.

        Args:
            payload: Raw request payload dictionary

        Returns:
            Task-specific response model

        Raises:
            ValueError: If validation fails
        """
        # 1. Validate request
        await self.validate_request(payload)

        # 2. Preprocess input
        input_data = (
            payload.get('input')
            or payload.get('audio')
            or payload.get('image')
        )
        if input_data:
            preprocessed_input = await self.preprocess_input(input_data)
            for key in ('input', 'audio', 'image'):
                if payload.get(key) is not None:
                    payload[key] = preprocessed_input
                    break

        # 3. Run inference
        response = await self.run_inference(payload)

        return response

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Validate the incoming request payload.
        Override in subclasses for task-specific validation.

        Args:
            payload: Raw request payload dictionary

        Raises:
            ValueError: If request is invalid
        """
        if payload is None:
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

    async def run_inference(
        self,
        payload: Dict[str, Any],
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> Any:
        result = await self.execute_triton_inference(payload, self._get_inference_model_class())
        postprocessed = await self.postprocess_output(
            result["response_data"], source_texts=result["source_texts"]
        )
        return self._build_response(payload, postprocessed)

    async def extract_field_from_items(
        self,
        items: List[Any],
        field_name: str,
    ) -> List[str]:
        """
        Extract a specific field from a list of items.
        Generic helper for extracting source texts or other fields from request items.

        Args:
            items: List of input items (dicts or objects with attributes)
            field_name: Name of the field to extract (e.g., 'source', 'audio', 'image')

        Returns:
            List of extracted field values as strings
        """
        extracted = []
        for item in items:
            if isinstance(item, dict):
                extracted.append(item.get(field_name, ''))
            elif hasattr(item, field_name):
                value = getattr(item, field_name)
                extracted.append(value if isinstance(value, str) else '')
            else:
                extracted.append('')
        return extracted

    async def execute_triton_inference(
        self,
        payload: Dict[str, Any],
        inference_model_class: type,
    ) -> Dict[str, Any]:
        try:
            # 1. Use pre-resolved service info injected at construction time
            service_id = self.service_info.get('service_id', '')
            model_name = self.service_info.get('name', '')
            triton_endpoint = self.service_info.get('endpoint', '')
            api_key = self.service_info.get('api_key')
            adapter_config = self.service_info.get('adapter_config')

            if not model_name or not triton_endpoint:
                raise RuntimeError(
                    f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                    "Ensure the Orchestrator resolved the service before creating this task service."
                )

            self.logger.debug(f"Converting payload to Triton format for model {model_name}")

            # 2. Instantiate inference model with adapter config
            inference_model = inference_model_class(adapter_config=adapter_config)

            # 3. Extract input and config from payload
            input_items = payload.get('input', [])
            config_data = payload.get('config', {})

            if not input_items:
                raise ValueError(f"{self.task_name}: payload 'input' is empty or missing")

            source_texts = await self.extract_field_from_items(input_items, 'source')

            # 4. Convert payload to Triton format using inference model
            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                input_items, config_data
            )

            # 5. Call Triton inference server
            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            # 6. Convert Triton output back to task format
            self.logger.debug("Converting Triton output to task response format")
            response_data = await inference_model.convert_triton_output_to_task_format(
                raw_triton_output
            )

            return {
                "response_data": response_data,
                "source_texts": source_texts,
                "service_id": service_id,
            }
        except Exception as e:
            self.logger.error(f"Triton inference execution failed: {str(e)}", exc_info=True)
            raise

    async def _call_triton_inference(
        self,
        triton_endpoint: str,
        triton_inputs: List[Dict[str, Any]],
        triton_outputs: List[str],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Triton inference server.
        Subclasses can override this for custom Triton communication.

        Args:
            triton_endpoint: Full inference URL
            triton_inputs: KServe v2 formatted input list
            triton_outputs: Expected output tensor names
            api_key: Optional API key for auth

        Returns:
            Raw output from Triton

        Raises:
            RuntimeError: If Triton call fails
        """
        from utils.http_client import HTTPServiceClient

        try:
            payload = {
                "inputs": triton_inputs,
                "outputs": [{"name": name} for name in triton_outputs],
            }

            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            self.logger.debug(f"Calling Triton: POST {triton_endpoint}")
            return await HTTPServiceClient(timeout=300).post_json(triton_endpoint, payload, headers)

        except Exception as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"Triton inference call failed at {triton_endpoint}: {str(e)}") from e
