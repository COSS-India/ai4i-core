"""
Task service interface and base class defining the contract for all inference task services.
"""

from abc import ABC, abstractmethod
import os
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
        serviceInfo: Optional[Dict[str, Any]] = None,
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

        
        # Shallow copy so preprocessing mutations don't affect the caller's original dict
        payload = dict(payload)

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
        if serviceInfo is not None:
            self.logger.debug("Using injected service_info for Triton inference")
            self.service_info = serviceInfo
        else:
            serviceInfo = self.service_info  # Fallback to self.service_info if not passed as argument

        response = await self.run_inference(payload, serviceInfo=serviceInfo)

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
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        result = await self.execute_triton_inference(payload, serviceInfo=serviceInfo)
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

    def get_payload_object(self, payload: Dict[str, Any]) -> List[Any]:
        """Return the modality input list from the raw payload.

        No default — every base class (TextBase/ImageBase/AudioBase) must
        implement this to read its own key ('input' / 'image' / 'audio').
        """
        raise NotImplementedError(
            f"{self.task_name} must implement get_payload_object"
        )

    async def execute_triton_inference(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        import time
        from trace.request_span import tracer, compute_total_time_ms
        from trace.span_attributes import get_input_type, get_output_type, count_input_tokens, count_output_tokens

        start_time = time.time()

        with tracer.start_as_current_span("ai-inference") as inference_span:
            try:
                # 1. Use pre-resolved service info injected at construction time
                serviceInfo = serviceInfo or {}
                service_id = serviceInfo.get('service_id', '')
                model_name = serviceInfo.get('name', '')
                triton_endpoint = serviceInfo.get('endpoint', '')
                api_key = serviceInfo.get('api_key')
                adapter_config = {
                        "inputs": [
                            {
                                "dtype": "BYTES",
                                "shape": [
                                    -1,
                                    1
                                ],
                                "tensor": "INPUT_TEXT",
                                "value_path": "input.source"
                            },
                            {
                                "dtype": "BYTES",
                                "shape": [
                                    -1,
                                    1
                                ],
                                "tensor": "INPUT_LANGUAGE_ID",
                                "value_path": "request.config.language.source_language"
                            },
                            {
                                "dtype": "BYTES",
                                "shape": [
                                    -1,
                                    1
                                ],
                                "tensor": "OUTPUT_LANGUAGE_ID",
                                "value_path": "request.config.language.target_language"
                            }
                        ],
                        "outputs": [
                            {
                                "dtype": "BYTES",
                                "tensor": "OUTPUT_TEXT",
                                "maps_to": "target"
                            }
                        ],
                        "version": "1.0",
                        "model_version": "1"
                    }#serviceInfo.get('adapter_config')

                if not model_name or not triton_endpoint:
                    raise RuntimeError(
                        f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                        "Ensure the Orchestrator resolved the service before creating this task service."
                    )

                self.logger.debug(f"Converting payload to Triton format for model {model_name}")

                # 2. Instantiate inference model with adapter config
                from services.base.config_mapper import GenericTritonMapper
                inference_model = GenericTritonMapper(adapter_config=adapter_config)

                # 3. Extract input and config from payload
                input_items = self.get_payload_object(payload)
                config_data = payload.get('config', {})

                if not input_items:
                    raise ValueError(f"{self.task_name}: input payload is empty or missing")

                source_texts = await self.extract_field_from_items(input_items, 'source')

                # Compute input metrics for ai-inference span
                input_type = get_input_type(payload)
                input_tokens = count_input_tokens(input_items, input_type)

                # 5. Convert payload to Triton format using inference model
                triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                    input_items, config_data
                )

                # 6. Call Triton inference server
                raw_triton_output = await self._call_triton_inference(
                    triton_endpoint=triton_endpoint,
                    triton_inputs=triton_inputs,
                    triton_outputs=triton_outputs,
                    api_key=api_key,
                )

                # 7. Convert Triton output back to task format
                self.logger.debug("Converting Triton output to task response format")
                response_data = await inference_model.convert_triton_output_to_task_format(
                    raw_triton_output
                )

                # Compute output metrics for ai-inference span
                output_type = get_output_type(response_data)
                output_tokens = count_output_tokens(response_data, output_type)

                # Set ai-inference span attributes
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "input_type": input_type,
                    "output_type": output_type,
                    "status": "success",
                    "status_code": 200,
                }
                for k, v in span_attrs.items():
                    inference_span.set_attribute(k, v)
                from trace.request_span import log_span_attributes
                log_span_attributes("ai-inference", inference_span, span_attrs)

                return {
                    "response_data": response_data,
                    "source_texts": source_texts,
                    "service_id": service_id,
                }
            except Exception as e:
                self.logger.error(f"Triton inference execution failed: {str(e)}", exc_info=True)
                # Set error status on span
                span_attrs = {
                    "total_time_ms": compute_total_time_ms(start_time),
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "input_type": get_input_type(payload),
                    "output_type": "unknown",
                    "status": "failure",
                    "status_code": 500,
                }
                for k, v in span_attrs.items():
                    inference_span.set_attribute(k, v)
                from trace.request_span import log_span_attributes
                log_span_attributes("ai-inference", inference_span, span_attrs)
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

            # TODO: Temporarily hardcoding 
            model_management_url = os.getenv("MODEL_MANAGEMENT_SERVICE_URL")
            triton_endpoint = f"{model_management_url}/v2/models/nmt/infer"
            return await HTTPServiceClient(timeout=300).post_json(triton_endpoint, payload, headers)
            # return await HTTPServiceClient(timeout=300).post_json(triton_endpoint, payload, headers)

        except Exception as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"Triton inference call failed at {triton_endpoint}: {str(e)}") from e
