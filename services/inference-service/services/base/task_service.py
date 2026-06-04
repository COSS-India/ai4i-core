"""
Base class defining the contract and shared pipeline for all inference task services.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PostProcessFormat:
    """
    Result of run_inference, consumed by postprocess_output.

    payload carries the (preprocessed) request so postprocess_output can echo
    config / build the task envelope without a second parameter.
    """
    payload: Dict[str, Any]
    response_data: List[Dict[str, Any]]
    source_texts: List[str] = field(default_factory=list)


class BaseTaskService:
    """
    Base class providing the common inference pipeline for all task services
    (Template Method pattern):

        process():
            validate_request(payload)                       # throws on bad input
            preprocessed = preprocess_input(payload)
            result: PostProcessFormat = run_inference(preprocessed)
            return postprocess_output(result)

    Subclasses set `payload_key` for their modality and implement
    postprocess_output(). They may override validate_request(),
    preprocess_input(), or run_inference() (e.g. AudioBase's per-item
    loop, TTS's per-chunk loop) as needed. process() is the template —
    never overridden.

    The resolved service dict (endpoint, model name, adapter_config, api_key)
    lives in self.service_info — injected via the constructor or adopted by
    process(). It is the single source of truth; pipeline methods read it
    from self, never from parameters.
    """

    # Modality input key in the raw payload: 'input' (text), 'audio', 'image'.
    # Set by the modality base classes (TextBase / AudioBase / ImageBase).
    payload_key: Optional[str] = None

    # Triton call topology: "batch" = one call for the whole input list;
    # "per_item" = one call per input item (audio models accept one file per
    # request). adapter_config may override with a "call_mode" key.
    TRITON_CALL_MODE: str = "batch"

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
        validate → preprocess → run_inference → postprocess_output.

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

        await self.validate_request(payload)
        preprocessed = await self.preprocess_input(payload)
        result = await self.run_inference(preprocessed)
        return await self.postprocess_output(result)

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

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the payload with its modality input list preprocessed.
        Identity by default — modality bases override with real preprocessing
        (text sanitization, audio/image URI resolution, ASR float decode),
        transforming payload[self.payload_key] in place and returning payload.
        Emptiness is rejected earlier by validate_request.
        """
        return payload

    async def postprocess_output(self, result: PostProcessFormat) -> Any:
        """
        Final step after inference. Scope: audit logging, observability, and
        truly model-specific final shaping — NOT Triton output conversion,
        which happens inside run_inference via the mapper.

        Default: unwrap scalar nesting, pair each output item with its input
        source, and echo the request config. Sufficient for services whose
        adapter_config already maps tensors to the response field names
        (e.g. NMT); override only when the task contract needs more.
        """
        output = []
        for idx, item in enumerate(result.response_data):
            clean = {k: self.unwrap_output_value(v) for k, v in item.items()}
            if "source" not in clean:
                clean["source"] = (
                    result.source_texts[idx] if idx < len(result.source_texts) else ""
                )
            output.append(clean)
        return {"output": output, "config": result.payload.get("config")}

    @staticmethod
    def unwrap_output_value(value: Any) -> Any:
        """
        Peel single-element list/tuple nesting and decode bytes to str.

        Triton KServe v2 returns tensors as flat lists (shape [1,1] → [["hi"]]);
        after mapping they may still be wrapped. Shared by postprocess_output
        implementations so each service doesn't hand-roll the same loop.
        """
        while isinstance(value, (list, tuple)) and len(value) == 1:
            value = value[0]
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return value

    def extract_field_from_items(
        self,
        items: List[Any],
        field_name: str,
    ) -> List[str]:
        """
        Extract a specific field from a list of items.
        Generic helper for extracting source texts or other fields from request items.

        Args:
            items: List of input item dicts
            field_name: Name of the field to extract (e.g. 'source')

        Returns:
            List of extracted field values as strings
        """
        return [item.get(field_name, '') for item in items]

    def _triton_context_builder(self):
        """
        Optional context builder fed to the mapper's value_path resolution
        (e.g. AudioBase exposes audio.audio_content, ASR exposes audio.samples).
        None = the mapper's canonical request/input/index context only.
        """
        return None

    async def convert_payload_to_triton_format(self, input_data, config):
        """Convert input items + config into KServe v2 Triton inputs.
        Default: adapter_config-driven via GenericTritonMapper. Override to
        normalise config first (call super) — see ASR / diarization."""
        from services.base.config_mapper import GenericTritonMapper
        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.compose_triton_kserve_v2_payload(
            input_data=input_data,
            config=config,
            context_builder=self._triton_context_builder(),
        )

    async def convert_triton_output_to_task_format(self, triton_output):
        """Map raw Triton output to task result dicts via adapter_config
        (including config-driven transforms like json_field)."""
        from services.base.config_mapper import GenericTritonMapper
        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.to_output_items(mapper.map_outputs(triton_output))

    async def run_inference(self, payload: Dict[str, Any]) -> PostProcessFormat:
        """
        Generic Triton inference — single implementation for every modality.

        Call topology is data/class-driven, not override-driven:
        adapter_config["call_mode"] or TRITON_CALL_MODE selects one batch
        call vs one call per item. Payload/tensor mapping goes through the
        convert_* hooks (mapper-backed by default). Item expansion (e.g.
        TTS chunking) happens in preprocess_input; merging expanded results
        back happens in postprocess_output — this method stays generic.
        """
        # Lazy import — trace setup happens at app init, after this module loads.
        from trace.request_span import traced_inference
        from trace.span_attributes import count_input_tokens, count_output_tokens, get_output_type

        async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
            model_name = self.service_info.get('name', '')
            triton_endpoint = self.service_info.get('endpoint', '')
            api_key = self.service_info.get('api_key')
            self._adapter_config = self.service_info.get('adapter_config')

            if not model_name or not triton_endpoint:
                raise RuntimeError(
                    f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                    "Ensure the Orchestrator resolved the service before creating this task service."
                )

            input_items = payload.get(self.payload_key) or []
            config_data = payload.get('config', {})
            if not input_items:
                raise ValueError(f"{self.task_name}: input payload is empty or missing")

            source_texts = self.extract_field_from_items(input_items, 'source')
            span_ctx["input_tokens"] = count_input_tokens(input_items, span_ctx["input_type"])

            call_mode = (
                (self._adapter_config or {}).get("call_mode")
                if isinstance(self._adapter_config, dict) else None
            ) or self.TRITON_CALL_MODE
            groups = [[item] for item in input_items] if call_mode == "per_item" else [input_items]

            response_data = []
            for group in groups:
                triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
                    group, config_data
                )
                raw_triton_output = await self._call_triton_inference(
                    triton_endpoint=triton_endpoint,
                    triton_inputs=triton_inputs,
                    triton_outputs=triton_outputs,
                    api_key=api_key,
                )
                response_data.extend(
                    await self.convert_triton_output_to_task_format(raw_triton_output)
                )

            span_ctx["output_type"] = get_output_type(response_data)
            span_ctx["output_tokens"] = count_output_tokens(response_data, span_ctx["output_type"])

            return PostProcessFormat(
                payload=payload,
                response_data=response_data,
                source_texts=source_texts,
            )

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
        from config import settings
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
            return await HTTPServiceClient(
                timeout=settings.DEFAULT_TRITON_TIMEOUT
            ).post_json(triton_endpoint, payload, headers)

        except Exception as e:
            self.logger.error(f"Failed to connect to Triton: {str(e)}")
            raise RuntimeError(f"Triton inference call failed at {triton_endpoint}: {str(e)}") from e
