"""
Task service interface and base class defining the contract for all inference task services.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

# TODO: import GenericTritonMapper from services.base.config_mapper once circular-import path is resolved


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

    @abstractmethod
    async def _deserialize_payload(self, payload: Dict[str, Any]) -> Any:
        """Deserialize raw payload — subclasses override for typed deserialization."""
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
        import logging
        from inference.inference_server_resolver import InferenceServerResolver
        
        self.task_name = self.__class__.__name__
        self.inference_server_resolver = InferenceServerResolver()
        self.logger = logging.getLogger(__name__)

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> Any:
        """Passthrough — subclasses override for typed deserialization."""
        return payload

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

    
    async def run_inference(self, payload: Dict[str, Any]) -> BaseModel:
        """
        Generic text inference pipeline:
          1. Call Triton via _run_triton_with_mapper
          2. Postprocess raw output
          3. Return result dict (model class wraps in typed response)
        """
        result = await self._run_triton_with_mapper(payload, source_field="source")
        self.logger.info(f"inference completed: service_id={result['service_id']}")
        return await self.postprocess_output(result)

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

    # TODO: execute_triton_inference is the old flow (uses inference_model_class).
    # Superseded by _run_triton_with_mapper. Remove once all callers are migrated.
    async def execute_triton_inference(
        self,
        config: Any,
        inference_model_class: type,
    ) -> Dict[str, Any]:
        try:
            # 1. Resolve service and model using config
            service_id, model_name, triton_endpoint, api_key, adapter_config = (
                await self._resolve_service_and_model(config)
            )

            self.logger.debug(f"Converting payload to Triton format for model {model_name}")

            # 2. Instantiate inference model with adapter config
            inference_model = inference_model_class(adapter_config=adapter_config)

            # 3. Get request payload from config for format conversion
            request_payload = getattr(config, '_request_payload', None)
            if not request_payload:
                raise ValueError("Config must have _request_payload attribute")

            # Extract source texts from request
            source_texts = await self.extract_field_from_items(request_payload.input, 'source')

            # Convert payload to Triton format using inference model
            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                request_payload.input, request_payload.config.dict()
            )

            # 4. Call Triton inference server
            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            # 5. Convert Triton output back to task format
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

    async def _resolve_service_and_model(
        self, config: Any
    ) -> Tuple[str, str, str, Optional[str], Optional[Any]]:
        """
        Resolve the model service details for the given NMT config.

        Returns:
            Tuple of (service_id, model_name, triton_endpoint, api_key, adapter_config).
        """
        service_id = config.service_id

        # If service_id not provided, could use SMR (Smart Model Router)
        # For now, default to configured service
        if not service_id:
            service_id = "indictrans-v2-all"
            self.logger.warning(f"No service_id provided, using default: {service_id}")

        # Resolve service using InferenceServerResolver
        self.logger.debug(f"Resolving service: {service_id}")
        try:
            service_info = await self.inference_server_resolver.resolve_service(service_id)
        except Exception as e:
            self.logger.error(
                f"Failed to resolve service {service_id}: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            raise RuntimeError(f"NMT: Failed to resolve service {service_id}: {str(e)}") from e

        # Extract fields from dict response
        model_name = service_info.get('name', '')
        triton_endpoint = service_info.get('endpoint', '')
        api_key = service_info.get('api_key')
        # adapter_config carries the tensor mapping (inputs/outputs) for this specific model
        adapter_config = service_info.get('adapter_config')

        if not model_name or not triton_endpoint:
            raise RuntimeError(
                "NMT: Invalid service info from resolver: missing model_name or triton_endpoint"
            )

        return (service_id, model_name, triton_endpoint, api_key, adapter_config)

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
            # Prepare request payload
            payload = {
                "inputs": triton_inputs,
                "outputs": [{"name": name} for name in triton_outputs],
            }

            # Add auth header if provided
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Make HTTP request to Triton
            self.logger.debug(f"Calling Triton: POST {triton_endpoint}")
            return await HTTPServiceClient(timeout=300).post_json(triton_endpoint, payload, headers)

        except Exception as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"Triton inference call failed at {triton_endpoint}: {str(e)}") from e


    def _get_from_payload(self, payload: Any, key: str, default: Any = None) -> Any:
        """Extract a field from payload regardless of whether it is a dict or an object."""
        if isinstance(payload, dict):
            return payload.get(key, default)
        return getattr(payload, key, default)

    async def _run_triton_with_mapper(
        self,
        payload: Any,
        source_field: str = "source",
    ) -> Dict[str, Any]:
        try:
            from types import SimpleNamespace

            config_raw = self._get_from_payload(payload, "config", {})
            input_data = self._get_from_payload(payload, "input", [])

            # _resolve_service_and_model expects attribute access (config.service_id)
            config = SimpleNamespace(**config_raw) if isinstance(config_raw, dict) else config_raw

            service_id, model_name, triton_endpoint, api_key, adapter_config = (
                await self._resolve_service_and_model(config)
            )

            self.logger.debug(f"Building Triton payload for model {model_name}")
            mapper = GenericTritonMapper(adapter_config)

            source_texts = await self.extract_field_from_items(input_data, source_field)

            triton_inputs, triton_outputs = mapper.compose_triton_kserve_v2_payload(
                input_data, config
            )

            self.logger.info(f"Calling Triton inference server: {triton_endpoint}")
            raw_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            mapped = mapper.map_outputs(raw_output)
            response_data = mapper.to_output_items(mapped)

            return {
                "response_data": response_data,
                "source_texts": source_texts,
                "service_id": service_id,
            }
        except Exception as e:
            self.logger.error(f"Triton inference failed: {str(e)}", exc_info=True)
            raise
