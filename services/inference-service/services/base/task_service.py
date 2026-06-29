"""
Base class defining the contract and shared pipeline for all inference task services.
"""

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from services.base.triton_input_mapper import InputTensorDeclaration, TritonInputMapper
from services.base.triton_output_mapper import OutputTensorDeclaration, TritonOutputMapper


class AdapterMappingConfig(BaseModel):
    """Adapter mapping contract: typed inputs + optional output expression.

    Parsed once per request in _build_mappers, then split into the input mapper
    (inputs) and output mapper (outputs + output_transform). Lives here with its
    only consumer; the per-direction tensor declarations live with their
    mappers, which stay independent of each other.
    """

    schema_version: str = Field(..., description="Adapter schema version, e.g. '2.0'")
    model_version: str = Field(default="1", description="Triton model version")
    inputs: List[InputTensorDeclaration] = Field(..., min_length=1)
    outputs: List[OutputTensorDeclaration] = Field(..., min_length=1)
    output_transform: Optional[str] = Field(
        default=None,
        description="JSONata expression mapping decoded tensors to the final "
        "task-type output. Omitted for code-output services (NER, TTS) that "
        "build their output in post_process from the decoded tensors.",
    )


@dataclass
class InferenceContext:
    """
    Carrier threaded through the task pipeline (validate -> preprocess ->
    run_inference -> post_process).

    payload carries the (preprocessed) request so post_process can echo config /
    build the task envelope without a second parameter. source_texts holds the
    paired input sources (used by code-output services like NER).

    run_inference fills raw_triton_outputs (the captured Triton responses),
    decoded_tensors (decoded + merged once, keyed by tensor name), and — for
    config-expressible services — transformed (the final task-type output the
    output_transform produces). Code-output services (NER, TTS) leave transformed
    unset in run_inference and build it in post_process from decoded_tensors /
    the raw responses.
    """
    payload: Dict[str, Any]
    source_texts: List[str] = field(default_factory=list)
    raw_triton_outputs: List[Dict[str, Any]] = field(default_factory=list)
    decoded_tensors: Dict[str, Any] = field(default_factory=dict)
    transformed: Optional[Any] = None


class BaseTaskService:
    """
    Base class providing the common inference pipeline for all task services
    (Template Method pattern):

        process():
            validate_request(payload)                       # throws on bad input
            preprocessed = preprocess_input(payload)
            result: InferenceContext = run_inference(preprocessed)
            result = post_process(result)                   # service-specific shaping
            return result.transformed                       # final HTTP body

    Subclasses set `payload_key` for their modality. Config-expressible services
    need no overrides: run_inference runs the adapter_config's output_transform
    and the base post_process is identity. Code-output services (NER, TTS)
    override post_process and build their output from the decoded tensors / raw
    responses. Modality bases (text/audio/image) override validate_request /
    preprocess_input.

    The resolved service dict (endpoint, model name, adapter_config, api_key)
    lives in self.service_info — injected via the constructor or adopted by
    process(). Pipeline methods read it from self, never from parameters.
    """

    # Modality input key in the raw payload: 'input' (text), 'audio', 'image'.
    payload_key: Optional[str] = None

    # Triton call topology: "batch" = one call for the whole input list;
    # "per_item" = one call per input item. Set by the modality base (audio is
    # per_item, text is batch); not data-driven.
    TRITON_CALL_MODE: str = "batch"

    # Per-item presence rules for validate_request. Each entry is a group of
    # field names; an item must carry at least one truthy field per group.
    # Set by the modality bases (text: ("source",); audio/image: content-or-uri).
    REQUIRED_ITEM_FIELDS: tuple = ()

    def __init__(self, service_info: Optional[Dict[str, Any]] = None):
        self.task_name = self.__class__.__name__
        self.service_info: Dict[str, Any] = service_info or {}
        self.logger = logging.getLogger(self.__class__.__module__)
        # Adapter config and its two mappers are resolved in run_inference
        # (after any service_info adopt).
        self._adapter_config: Optional[Dict[str, Any]] = None
        self._input_mapper: Optional[TritonInputMapper] = None
        self._output_mapper: Optional[TritonOutputMapper] = None

    def _build_mappers(self) -> None:
        """Parse the adapter_config once and build the input and output mappers.

        Built per request, so any compiled JSONata expression is never shared
        across threads. The input mapper renders typed Triton inputs; the output
        mapper owns the output tensor names, decode, and the output_transform.
        """
        cfg = self._adapter_config
        if not isinstance(cfg, AdapterMappingConfig):
            cfg = AdapterMappingConfig.model_validate(cfg)
        self._input_mapper = TritonInputMapper(cfg.inputs)
        self._output_mapper = TritonOutputMapper(cfg.outputs, cfg.output_transform)

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute the complete inference pipeline (Template Method).
        validate → preprocess → run_inference → post_process.

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
        result = await self.post_process(result)
        return result.transformed

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Generic request validation, driven by class declarations:
          - the modality input list (payload[payload_key]) must be non-empty
          - each item must carry at least one truthy field per
            REQUIRED_ITEM_FIELDS group

        Per-modality presence is declared, not coded. Required Triton inputs
        (sourceLanguage, audioContent, ...) are enforced by the input mapper (a
        missing required value_path raises ValueError -> 400). Cross-field or
        config rules (language equality, transliteration conflict) go in a
        modality/service override: call super() for this generic check, then
        stitch together the validation helpers it needs (e.g. _get_nested).
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

    async def preprocess_input(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return the payload with its modality input list preprocessed.
        Identity by default — modality bases override with real preprocessing.
        """
        return payload

    async def post_process(self, result: InferenceContext) -> InferenceContext:
        """
        Post-inference shaping hook. Identity by default: run_inference already
        set result.transformed (the output_transform's task-type output) for
        config-expressible services, so process() returns it as-is.

        Code-output services (NER, TTS) override this to build result.transformed
        themselves from the tensors decoded once in run_inference
        (result.decoded_tensors, or the raw responses for TTS's waveform DSP).
        """
        return result

    def extract_field_from_items(
        self,
        items: List[Any],
        field_name: str,
    ) -> List[str]:
        """Extract a field (e.g. 'source') from each input item as a string."""
        return [item.get(field_name, '') for item in items]

    @staticmethod
    def _get_nested(data: Any, path: str, default: Any = None) -> Any:
        """Look up a dotted key path in a nested dict, e.g.
        _get_nested(payload, "config.language.sourceLanguage"). Returns default
        if any segment is missing or not a dict. One generic accessor so
        services don't grow a getter per field."""
        current = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    @staticmethod
    def _validate_external_url(url: str) -> None:
        """SSRF guard for user-supplied download URIs (OWASP API7).

        Audio/image items may carry an audioUri/imageUri the service fetches
        server-side. Without validation a caller could make the service request
        internal endpoints (cloud metadata, localhost admin ports, RFC-1918
        hosts). Enforces http(s) scheme and public-address resolution only.
        ALLOW_PRIVATE_DOWNLOAD_HOSTS=true disables the address check for local
        development.

        Raises:
            ValueError: If the scheme is not http(s), the host is missing,
                cannot be resolved, or resolves to a non-public address.
        """
        from config import settings

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed; use http(s)")
        if not parsed.hostname:
            raise ValueError("URL has no hostname")

        if settings.ALLOW_PRIVATE_DOWNLOAD_HOSTS:
            return

        try:
            addr_infos = socket.getaddrinfo(parsed.hostname, None)
        except socket.gaierror as exc:
            raise ValueError(f"Cannot resolve host '{parsed.hostname}'") from exc

        for info in addr_infos:
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(
                    f"Host '{parsed.hostname}' resolves to a non-public address; "
                    "downloads from internal networks are not allowed"
                )

    async def convert_payload_to_triton_format(self, input_data, config):
        """Render input items + config into the KServe v2 Triton inputs list,
        via the input mapper. value_paths read input.<field>, so preprocessing
        exposes derived fields (e.g. ASR samples) just by writing them onto the
        input item. The output tensor names to request come from the output
        mapper, not here."""
        return self._input_mapper.compose_triton_kserve_v2_payload(
            input_data=input_data, config=config
        )

    async def run_inference(self, payload: Dict[str, Any]) -> InferenceContext:
        """
        Generic Triton inference — single implementation for every modality.

        Call topology is class-driven: TRITON_CALL_MODE selects one batch call
        vs one call per item. Input mapping goes through the convert hook; the
        decoded tensors are run through the output_transform here, so this
        returns the final task-type output for config-expressible services. Item
        expansion (e.g. TTS chunking) happens in preprocess_input; code-output
        services (NER, TTS) shape the output in post_process.
        """
        # Lazy import — trace setup happens at app init, after this module loads.
        from trace.request_span import traced_inference, traced_span
        from trace.span_attributes import count_input_tokens

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

            if not self._adapter_config:
                raise RuntimeError(
                    f"{self.task_name}: service '{model_name}' has no adapter_config. "
                    "Add adapterConfig to the model's inferenceEndPoint via the Model Management API "
                    "or the platform model registration form."
                )

            self._build_mappers()

            input_items = payload.get(self.payload_key) or []
            config_data = payload.get('config', {})
            if not input_items:
                raise ValueError(f"{self.task_name}: input payload is empty or missing")

            source_texts = self.extract_field_from_items(input_items, 'source')
            span_ctx["input_tokens"] = count_input_tokens(input_items, span_ctx["input_type"])

            groups = (
                [[item] for item in input_items]
                if self.TRITON_CALL_MODE == "per_item"
                else [input_items]
            )

            triton_outputs = self._output_mapper.output_names
            raw_outputs: List[Dict[str, Any]] = []
            for group in groups:
                triton_inputs = await self.convert_payload_to_triton_format(
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

            # Decode the Triton tensors once here; the trace metric, the output
            # transform, and code-output services (NER, TTS) all read this.
            decoded = self._output_mapper.decode(raw_outputs)
            output_type, output_tokens = self._estimate_output(decoded)
            span_ctx["output_type"] = output_type
            span_ctx["output_tokens"] = output_tokens

            # Config-expressible services get their final output here; code-output
            # services (no output_transform) build it in post_process.
            transformed = (
                self._output_mapper.transform(decoded, input_items, config_data)
                if self._output_mapper.has_transform
                else None
            )

            return InferenceContext(
                payload=payload,
                source_texts=source_texts,
                raw_triton_outputs=raw_outputs,
                decoded_tensors=decoded,
                transformed=transformed,
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
        from http_client import HTTPServiceClient

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
