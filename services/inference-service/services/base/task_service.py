"""
Base class defining the contract and shared pipeline for all inference task services.
"""

import logging
from typing import Any, Dict, List, Optional


class BaseTaskService:
    """
    Base class providing the common inference pipeline for all task services
    (Template Method pattern):

        process() → validate_request → preprocess_input
                  → execute_triton_inference → postprocess

    Subclasses set `payload_key` for their modality and implement
    postprocess(). They may override validate_request(),
    preprocess_input(), or execute_triton_inference() (e.g. AudioBase's
    per-item loop, TTS's per-chunk loop) as needed. process() is the
    template — never overridden.

    The resolved service dict (endpoint, model name, adapter_config, api_key)
    lives in self.service_info — injected via the constructor or adopted by
    process(). It is the single source of truth; pipeline methods read it
    from self, never from parameters.
    """

    # Modality input key in the raw payload: 'input' (text), 'audio', 'image'.
    # Set by the modality base classes (TextBase / AudioBase / ImageBase).
    payload_key: Optional[str] = None

    def __init__(self, service_info: Optional[Dict[str, Any]] = None):
        """
        Initialize base task service.

        Args:
            service_info: Pre-resolved service dict injected by the Orchestrator/Factory
                          (contains endpoint, model name, adapter_config, api_key, etc.).
        """
        self.task_name = self.__class__.__name__
        self.service_info: Dict[str, Any] = service_info or {}
        # Logger named after the concrete service's module (e.g. services.nmt_service)
        # so subclasses don't need an __init__ just to set their logger.
        self.logger = logging.getLogger(self.__class__.__module__)

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute the complete inference pipeline (Template Method).
        validate → preprocess → execute_triton_inference → postprocess.

        This is the main entry point - Orchestrator calls this method with raw payload.

        Args:
            payload: Raw request payload dictionary
            serviceInfo: Optional resolved service dict; when provided it is
                         adopted as self.service_info for this and later calls.

        Returns:
            Task-specific response (dict or response model)

        Raises:
            ValueError: If validation fails
        """
        if serviceInfo is not None:
            self.logger.debug("Adopting injected service_info for Triton inference")
            self.service_info = serviceInfo

        # Shallow copy so preprocessing mutations don't affect the caller's original dict
        payload = dict(payload)

        # 1. Validate request
        await self.validate_request(payload)

        # 2. Preprocess the modality input list (payload[self.payload_key])
        input_data = payload.get(self.payload_key) or []
        if input_data:
            payload[self.payload_key] = await self.preprocess_input(input_data)

        # 3. Run inference, then shape the response
        result = await self.execute_triton_inference(payload)
        return await self.postprocess(
            payload, result["response_data"], result["source_texts"]
        )

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
        Identity by default — modality bases override with real preprocessing
        (text sanitization, audio/image URI resolution, ASR float decode).
        process() only calls this with a non-empty input list; emptiness is
        rejected earlier by validate_request.
        """
        return input_data

    async def postprocess(
        self,
        payload: Dict[str, Any],
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> Any:
        """
        Build the task response from mapped Triton output:
        shape the output items AND assemble the response envelope
        (taskType, config echo) in one place.

        Args:
            payload: Original request payload (for config echo)
            response_items: Output dicts from convert_triton_output_to_task_format
            source_texts: Parallel list of input sources (text) or audio URIs

        Returns:
            Task-specific response (dict or typed model)
        """
        raise NotImplementedError(
            f"{self.task_name} must implement postprocess"
        )

    @staticmethod
    def unwrap_output_value(value: Any) -> Any:
        """
        Peel single-element list/tuple nesting and decode bytes to str.

        Triton KServe v2 returns tensors as flat lists (shape [1,1] → [["hi"]]);
        after mapping they may still be wrapped. Shared by postprocess
        implementations so each service doesn't hand-roll the same loop.
        """
        while isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return value

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

    async def execute_triton_inference(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generic adapter_config-driven Triton inference: one Triton call for the
        whole input batch, mapped via GenericTritonMapper.

        Reads the resolved service from self.service_info.
        Override for modality-specific loops (see AudioBase / TTS).

        Returns:
            {"response_data": [...], "source_texts": [...], "service_id": str}
        """
        from services.base.config_mapper import GenericTritonMapper
        # Lazy import — trace setup happens at app init, after this module loads.
        from trace.request_span import traced_inference
        from trace.span_attributes import count_input_tokens, count_output_tokens, get_output_type

        async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
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
            inference_model = GenericTritonMapper(adapter_config=adapter_config)

            input_items = payload.get(self.payload_key) or []
            config_data = payload.get('config', {})
            if not input_items:
                raise ValueError(f"{self.task_name}: input payload is empty or missing")

            source_texts = await self.extract_field_from_items(input_items, 'source')
            span_ctx["input_tokens"] = count_input_tokens(input_items, span_ctx["input_type"])

            triton_inputs, triton_outputs = await inference_model.convert_payload_to_triton_format(
                input_items, config_data
            )

            raw_triton_output = await self._call_triton_inference(
                triton_endpoint=triton_endpoint,
                triton_inputs=triton_inputs,
                triton_outputs=triton_outputs,
                api_key=api_key,
            )

            self.logger.debug("Converting Triton output to task response format")
            response_data = await inference_model.convert_triton_output_to_task_format(
                raw_triton_output
            )

            span_ctx["output_type"] = get_output_type(response_data)
            span_ctx["output_tokens"] = count_output_tokens(response_data, span_ctx["output_type"])

            return {
                "response_data": response_data,
                "source_texts": source_texts,
                "service_id": service_id,
            }

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
