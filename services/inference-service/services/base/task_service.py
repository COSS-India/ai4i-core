"""
Base class defining the contract and shared pipeline for all inference task services.
"""

import json
import logging
from dataclasses import dataclass, field
from tarfile import HeaderError
from typing import Any, Dict, List, Optional

# ── Persistent Triton HTTP client (Fix 5) ────────────────────────────────────
# One shared httpx.AsyncClient reuses TCP connections across Triton calls instead
# of opening and closing a new connection on every request.
_TRITON_CLIENT: Optional[Any] = None  # httpx.AsyncClient, imported lazily


def _get_triton_client() -> Any:
    global _TRITON_CLIENT
    if _TRITON_CLIENT is None:
        import httpx
        _TRITON_CLIENT = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
    return _TRITON_CLIENT


async def close_triton_client() -> None:
    """Close the shared Triton client; called from the app lifespan on shutdown."""
    global _TRITON_CLIENT
    if _TRITON_CLIENT is not None:
        await _TRITON_CLIENT.aclose()
        _TRITON_CLIENT = None


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
        result = await self.run_inference(preprocessed, serviceInfo)
        response = await self.postprocess_output(result)
        if isinstance(response, dict):
            response["model"] = self._build_model_metadata()
        return response

    def _build_model_metadata(self) -> Dict[str, Any]:
        """
        Model identity metadata (models/common.py ModelMetadata), resolved
        from mm_models via service_info. Attached to every task-service
        response so API/portal clients can echo modelProvider/modelVersion
        into the Feedback API without a second lookup.
        """
        info = self.service_info
        return {
            "modelProvider": info.get("model_provider"),
            "modelVersion": info.get("model_version"),
            "language": info.get("language") or [],
        }

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        """
        Hook: validate the incoming request payload; raise ValueError on bad
        input. No-op anchor for the super() chain — the routes layer already
        guarantees payload is a dict (FastAPI body validation), and the real
        checks live in the modality bases (text/audio/image) and task
        overrides on top of them.
        """

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

        When the adapter_config declares response shaping (response_key /
        pair_with_input on any output tensor, or a response envelope block),
        the shaping is config-driven instead — declared renames, splats,
        input pairings, static fields, and envelope replace the implicit
        "source" pairing above.
        """
        if isinstance(self._adapter_config, dict) and (
            self._adapter_config.get("response")
            or any(
                o.get("response_key") or o.get("pair_with_input")
                for o in self._adapter_config.get("outputs", [])
            )
        ):
            from services.base.config_mapper import GenericTritonMapper
            mapper = GenericTritonMapper(self._adapter_config)
            shaped = mapper.shape_output_items(
                result.response_data,
                result.payload.get(self.payload_key) or [],
            )
            return mapper.build_response_envelope(
                shaped, result.payload.get("config")
            )

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

    async def run_inference(self, payload: Dict[str, Any], serviceInfo: Dict[str, Any]) -> PostProcessFormat:
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

        model_name = serviceInfo.get('name', '')
        triton_endpoint = serviceInfo.get('endpoint', '')
        api_key = serviceInfo.get('api_key')
        service_id = serviceInfo.get('serviceId', '')
        self._adapter_config = serviceInfo.get('adapter_config')
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
            #// call ai_inference span here. So that it will geenrate teace time taken for ai inference only.
            async with traced_inference(payload, self.task_name, self.logger) as span_ctx:
                # service_id is not in context vars — must be copied explicitly.
                # The PPU Kafka consumer reads only the ai-inference span for
                # billing, so it must always be present there (mirrors llm_service.py).
                span_ctx["service_id"] = service_id
                # Must count only this group's items, not the full input_items list —
                # otherwise per_item call_mode bills the whole request once per item.
                span_ctx["input_tokens"] = count_input_tokens(group, span_ctx["input_type"])
                raw_triton_output = await self._call_triton_inference(
                    triton_endpoint=triton_endpoint,
                    triton_inputs=triton_inputs,
                    triton_outputs=triton_outputs,
                    api_key=api_key,
                )
                group_response_data = await self.convert_triton_output_to_task_format(raw_triton_output)
                response_data.extend(group_response_data)
                span_ctx["output_type"] = get_output_type(group_response_data)
                # Recorded on the span for observability/trace inspection, but
                # PPU billing for non-LLM services is input-only by design — the
                # Kafka consumer (payperuse_consumer/handler.py) ignores this
                # field for every inference_name except llm.
                span_ctx["output_tokens"] = count_output_tokens(group_response_data, span_ctx["output_type"])
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

        try:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Endpoint URL deliberately omitted from log message — it
            # identifies internal infra (Triton host/port + model name)
            # and would leak via the Logs Dashboard pipeline. The traced
            # span carries the model_name attribute when correlation is
            # needed server-side.
            self.logger.debug("Calling Triton (model=%s)", self.service_info.get("name", ""))

            client = _get_triton_client()

            # Inputs carrying raw bytes (e.g. ASR AUDIO_SIGNAL float samples)
            # use the KServe binary tensor extension: raw bytes appended after
            # a JSON header, avoiding multi-MB JSON float serialization.
            if any("_raw" in inp for inp in triton_inputs):
                body, binary_headers = self._build_binary_request(triton_inputs, triton_outputs)
                headers.update(binary_headers)
                response = await client.post(
                    triton_endpoint,
                    content=body,
                    headers=headers,
                    timeout=settings.DEFAULT_TRITON_TIMEOUT,
                )
            else:
                payload = {
                    "inputs": triton_inputs,
                    "outputs": [{"name": name} for name in triton_outputs],
                }
                response = await client.post(
                    triton_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=settings.DEFAULT_TRITON_TIMEOUT,
                )
            if response.status_code == 404:
                raise LookupError("Triton endpoint not found")
            response.raise_for_status()
            return response.json()

        except Exception as e:
            # Log only the exception TYPE — httpx/urllib3 error reprs embed
            # the request URL, which would leak the Triton endpoint into
            # any log sink (Logs Dashboard, etc.). Full traceback is still
            # captured by the upstream `exc_info=True` log in routes/inference.py.
            self.logger.error(
                "Triton inference call failed for task=%s: %s",
                self.task_name, type(e).__name__,
            )
            # Don't embed triton_endpoint or str(e) in the RuntimeError
            # message — the exception message can surface in logs ingested
            # to client-visible sinks. The chained `from e` preserves the
            # original exception for server-side debugging only.
            raise RuntimeError(
                f"{self.task_name}: Triton inference call failed"
            ) from e

    @staticmethod
    def _build_binary_request(triton_inputs, triton_outputs):
        """Assemble a KServe v2 binary tensor request (header + raw bytes).

        Inputs carrying '_raw' bytes are declared with binary_data_size and
        their bytes appended after the JSON header, in input order. Outputs are
        requested as JSON (binary_data: false) so the response parses normally.

        Returns (body_bytes, extra_headers).
        """
        header_inputs = []
        raw_chunks = []
        for inp in triton_inputs:
            if "_raw" in inp:
                raw = inp["_raw"]
                header_inputs.append({
                    "name": inp["name"],
                    "datatype": inp["datatype"],
                    "shape": inp["shape"],
                    "parameters": {"binary_data_size": len(raw)},
                })
                raw_chunks.append(raw)
            else:
                header_inputs.append(inp)
        header = {
            "inputs": header_inputs,
            "outputs": [
                {"name": name, "parameters": {"binary_data": False}}
                for name in triton_outputs
            ],
        }
        header_bytes = json.dumps(header).encode("utf-8")
        body = header_bytes + b"".join(raw_chunks)
        return body, {
            "Content-Type": "application/octet-stream",
            "Inference-Header-Content-Length": str(len(header_bytes)),
        }
