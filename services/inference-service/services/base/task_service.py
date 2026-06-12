"""
Base class defining the contract and shared pipeline for all inference task services.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.base.jsonata_mapper import build_mapper


@dataclass
class InferenceContext:
    """
    Carrier threaded through the task pipeline (validate -> preprocess ->
    run_inference -> produce_result -> build_envelope).

    payload carries the (preprocessed) request so produce_result can echo
    config / build the task envelope without a second parameter. source_texts
    holds the paired input sources (used by code-output services like NER).
    service_info and mapper expose the resolved service and the single
    per-request Triton mapper. raw_triton_outputs holds the captured Triton
    responses; produce_result turns them into the final output via the mapper's
    output_transform (transformed) or, for code-output services, into
    result_items the service builds itself.
    """
    payload: Dict[str, Any]
    source_texts: List[str] = field(default_factory=list)
    service_info: Dict[str, Any] = field(default_factory=dict)
    mapper: Optional[Any] = None
    # Code-output services (NER, TTS) populate this; build_envelope reads it.
    result_items: List[Dict[str, Any]] = field(default_factory=list)
    # Raw Triton responses captured in run_inference, and the final task-type
    # output the output_transform produces.
    raw_triton_outputs: List[Dict[str, Any]] = field(default_factory=list)
    transformed: Optional[Any] = None


class BaseTaskService:
    """
    Base class providing the common inference pipeline for all task services
    (Template Method pattern):

        process():
            validate_request(payload)                       # throws on bad input
            preprocessed = preprocess_input(payload)
            result: InferenceContext = run_inference(preprocessed)
            result = produce_result(result)                 # tensors -> task output
            return build_envelope(result)                   # task output -> HTTP body

    Subclasses set `payload_key` for their modality. Config-expressible services
    need no overrides: the adapter_config's output_transform produces the task
    output. Code-output services (NER, TTS) override produce_result/build_envelope
    and read the mapper's decoded tensors directly. Modality bases
    (text/audio/image) override validate_request / preprocess_input.

    The resolved service dict (endpoint, model name, adapter_config, api_key)
    lives in self.service_info — injected via the constructor or adopted by
    process(). Pipeline methods read it from self, never from parameters.
    """

    # Modality input key in the raw payload: 'input' (text), 'audio', 'image'.
    payload_key: Optional[str] = None

    # Triton call topology: "batch" = one call for the whole input list;
    # "per_item" = one call per input item. adapter_config may override with
    # a "call_mode" key.
    TRITON_CALL_MODE: str = "batch"

    # Per-item presence rules for validate_request. Each entry is a group of
    # field names; an item must carry at least one truthy field per group.
    # Set by the modality bases (text: ("source",); audio/image: content-or-uri).
    REQUIRED_ITEM_FIELDS: tuple = ()

    def __init__(self, service_info: Optional[Dict[str, Any]] = None):
        self.task_name = self.__class__.__name__
        self.service_info: Dict[str, Any] = service_info or {}
        self.logger = logging.getLogger(self.__class__.__module__)
        # Adapter config and its mapper are resolved in run_inference (after any
        # service_info adopt).
        self._adapter_config: Optional[Dict[str, Any]] = None
        self._mapper: Optional[Any] = None

    def _get_mapper(self):
        """Build the adapter-config mapper once per request and reuse it.

        Built per request, so the compiled JSONata expression is never shared
        across threads. Shared by the input hook and produce_result so
        adapter_config is parsed a single time per request.
        """
        if self._mapper is None:
            self._mapper = build_mapper(self._adapter_config)
        return self._mapper

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute the complete inference pipeline (Template Method).
        validate → preprocess → run_inference → produce_result → build_envelope.

        Orchestrator calls this with the raw payload and the resolved service.
        """
        if serviceInfo is not None:
            self.logger.debug("Adopting injected service_info for Triton inference")
            self.service_info = serviceInfo

        # Shallow copy so preprocessing mutations don't affect the caller's original dict
        payload = dict(payload)

        await self.validate_request(payload)
        preprocessed = await self.preprocess_input(payload)
        result = await self.run_inference(preprocessed)
        result = await self.produce_result(result)
        return self.build_envelope(result)

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Generic request validation, driven by class declarations:
          - the modality input list (payload[payload_key]) must be non-empty
          - each item must carry at least one truthy field per
            REQUIRED_ITEM_FIELDS group

        Per-modality presence is declared, not coded. Required Triton inputs
        (sourceLanguage, audioContent, ...) are enforced by the renderer (a
        missing required value_path raises ValueError -> 400), so services need
        no field-presence overrides. Cross-field or config rules go in the
        validate_config hook (text language equality, transliteration conflict).
        """
        items = payload.get(self.payload_key)
        if not items:
            raise ValueError(f"{self.task_name}: {self.payload_key} list cannot be empty")
        for idx, item in enumerate(items):
            for group in self.REQUIRED_ITEM_FIELDS:
                if not any(item.get(field) for field in group):
                    req = " or ".join(group)
                    raise ValueError(
                        f"{self.task_name}: {self.payload_key}[{idx}] requires {req}"
                    )
        await self.validate_config(payload)

    async def validate_config(self, payload: Dict[str, Any]) -> None:
        """Hook for cross-field / config validation (and config derivation).
        No-op by default; TextBase checks language rules, Transliteration adds
        its numSuggestions/isSentence rule."""

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the payload with its modality input list preprocessed.
        Identity by default — modality bases override with real preprocessing.
        """
        return payload

    async def produce_result(self, result: InferenceContext) -> InferenceContext:
        """
        Turn the captured Triton responses into the final task-type output by
        running the adapter_config's output_transform (JSONata) over the decoded
        tensors. build_envelope returns it as-is.

        Code-output services (NER, TTS) override this: they read
        self._get_mapper().decode(result.raw_triton_outputs) and run their
        algorithm/DSP, setting result.result_items.
        """
        result.transformed = self._get_mapper().transform(
            result.raw_triton_outputs,
            result.payload.get(self.payload_key) or [],
            result.payload.get("config"),
        )
        return result

    def build_envelope(self, result: InferenceContext) -> Any:
        """
        Terminal step: return the task-type output produced by the
        output_transform. Code-output services override to assemble their
        envelope from result.result_items.
        """
        return result.transformed

    def extract_field_from_items(
        self,
        items: List[Any],
        field_name: str,
    ) -> List[str]:
        """Extract a field (e.g. 'source') from each input item as a string."""
        return [item.get(field_name, '') for item in items]

    async def convert_payload_to_triton_format(self, input_data, config):
        """Convert input items + config into KServe v2 Triton inputs + the
        output tensor names to request. adapter_config-driven via the mapper.
        value_paths read input.<field>, so preprocessing exposes derived fields
        (e.g. ASR samples) just by writing them onto the input item."""
        return self._get_mapper().compose_triton_kserve_v2_payload(
            input_data=input_data, config=config
        )

    async def run_inference(self, payload: Dict[str, Any]) -> InferenceContext:
        """
        Generic Triton inference — single implementation for every modality.

        Call topology is data/class-driven: adapter_config["call_mode"] or
        TRITON_CALL_MODE selects one batch call vs one call per item. Input
        mapping goes through the convert hook; the raw Triton responses are
        captured for produce_result. Item expansion (e.g. TTS chunking) happens
        in preprocess_input; merging happens in produce_result.
        """
        # Lazy import — trace setup happens at app init, after this module loads.
        from trace.request_span import traced_inference, traced_span
        from trace.span_attributes import count_input_tokens

        async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
            model_name = self.service_info.get('name', '')
            triton_endpoint = self.service_info.get('endpoint', '')
            api_key = self.service_info.get('api_key')
            self._adapter_config = self.service_info.get('adapter_config')
            self._mapper = None

            if not model_name or not triton_endpoint:
                raise RuntimeError(
                    f"{self.task_name}: service_info is missing 'name' or 'endpoint'. "
                    "Ensure the Orchestrator resolved the service before creating this task service."
                )

            if not self._adapter_config:
                raise RuntimeError(
                    f"{self.task_name}: service '{model_name}' has no adapter_config. "
                    "Add adapterConfig to the model's inferenceEndPoint via the Model Management API "
                    "or the platform model registration form."
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

            raw_outputs: List[Dict[str, Any]] = []
            for group in groups:
                triton_inputs, triton_outputs = await self.convert_payload_to_triton_format(
                    group, config_data
                )
                # Child span around the Triton call only, so the trace shows
                # pure model-server time, isolated from the tensor mapping.
                with traced_span("triton-inference"):
                    raw_triton_output = await self._call_triton_inference(
                        triton_endpoint=triton_endpoint,
                        triton_inputs=triton_inputs,
                        triton_outputs=triton_outputs,
                        api_key=api_key,
                    )
                raw_outputs.append(raw_triton_output)

            output_type, output_tokens = self._estimate_output(
                self._get_mapper().decode(raw_outputs)
            )
            span_ctx["output_type"] = output_type
            span_ctx["output_tokens"] = output_tokens

            return InferenceContext(
                payload=payload,
                source_texts=source_texts,
                service_info=self.service_info,
                mapper=self._mapper,
                raw_triton_outputs=raw_outputs,
            )

    @staticmethod
    def _estimate_output(decoded: Dict[str, Any]) -> tuple:
        """Cheap output-modality + token estimate for the trace span, from the
        decoded tensors (keyed by tensor name). Text -> word count; numeric
        (waveform) -> samples/160; otherwise unknown. One pass per tensor, no
        per-sample allocation."""
        words = 0
        samples = 0
        for values in decoded.values():
            vals = values if isinstance(values, list) else [values]
            head = next((v for v in vals if v is not None), None)
            if isinstance(head, str):
                words += sum(len(v.split()) for v in vals if isinstance(v, str))
            elif isinstance(head, bool):
                continue
            elif isinstance(head, (int, float)):
                samples += len(vals)
            elif isinstance(head, (dict, list)):
                words += len(str(head).split())
        if words:
            return "text", words
        if samples:
            return "audio", max(samples // 160, 1)
        return "unknown", 0

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

            # Endpoint URL deliberately omitted from log message — it
            # identifies internal infra (Triton host/port + model name)
            # and would leak via the Logs Dashboard pipeline.
            self.logger.debug("Calling Triton (model=%s)", self.service_info.get("name", ""))
            return await HTTPServiceClient(
                timeout=settings.DEFAULT_TRITON_TIMEOUT
            ).post_json(triton_endpoint, payload, headers)

        except Exception as e:
            # Log only the exception TYPE — httpx/urllib3 error reprs embed
            # the request URL, which would leak the Triton endpoint.
            self.logger.error(
                "Triton inference call failed for task=%s: %s",
                self.task_name, type(e).__name__,
            )
            raise RuntimeError(
                f"{self.task_name}: Triton inference call failed"
            ) from e
