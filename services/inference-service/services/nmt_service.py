"""NMT (Neural Machine Translation) TaskService implementation."""

import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.nmt import (
    NMTInferenceRequest,
    NMTInferenceResponse,
)
from ai4icore_core.telemetry import async_trace_stage

logger = logging.getLogger(__name__)


class NMTTaskService(TextBase):
    """
    TaskService for Neural Machine Translation inference.
    Handles translation requests between language pairs.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        """
        Initialize NMT task service.

        Args:
            service_info: Pre-resolved service dict from Orchestrator (endpoint, model
                          name, adapter_config, api_key).  Forwarded to BaseTaskService
                          so execute_triton_inference can use it without re-resolving.
        """
        super().__init__(service_info=service_info)
        self.triton_client = None  # Initialized on first use
        self.logger = logger

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
        try:
            from models.schemas.nmt import TextInput, NMTConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = NMTConfig(**config_data)

            return NMTInferenceRequest(
                input=input_items,
                config=config_data
            )
        except Exception as e:
            raise ValueError(f"NMT: Failed to deserialize payload: {str(e)}")

    @async_trace_stage("validate")
    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        # Convert to dict for validation
        request_dict = request.dict() if hasattr(request, 'dict') else request.__dict__

        input_items = request_dict.get('input', [])
        if not input_items:
            raise ValueError("NMT: input array cannot be empty")

        for idx, item in enumerate(input_items):
            source = item.get('source') if isinstance(item, dict) else getattr(item, 'source', None)
            if not source or not isinstance(source, str):
                raise ValueError(f"NMT: input[{idx}]['source'] must be non-empty string")

        config_dict = request_dict.get('config', {})
        language_dict = config_dict.get('language', {}) if isinstance(config_dict, dict) else getattr(config_dict, 'language', {})
        
        source_lang = language_dict.get('source_language') if isinstance(language_dict, dict) else getattr(language_dict, 'source_language', None)
        target_lang = language_dict.get('target_language') if isinstance(language_dict, dict) else getattr(language_dict, 'target_language', None)
        
        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")

        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(f"NMT request validated: {source_lang} -> {target_lang} ({len(input_items)} inputs)")
    @async_trace_stage("preprocess_input")
    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        preprocessed = await super().preprocess_input(input_data)

        cleaned = []
        for item in preprocessed:
            source_text = item.get('source', '')
            normalized = ' '.join(source_text.split())
            normalized = normalized.strip()
            cleaned.append({
                'source': normalized,
                **{k: v for k, v in item.items() if k != 'source'}
            })

        self.logger.debug(f"NMT preprocessed {len(cleaned)} inputs")
        return cleaned

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    def _build_response(
        self, request: NMTInferenceRequest, postprocessed: Dict[str, Any]
    ) -> NMTInferenceResponse:
        return NMTInferenceResponse(
            output=postprocessed["output"],
            smr_response=None,
        )

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Pair mapped output items with their source texts to build the final response.

        Args:
            response_items: List[Dict] from convert_triton_output_to_task_format().
                Each dict has keys matching 'maps_to' in adapter_config outputs
                (e.g. {"target": "translated text"}).
            source_texts: Original input texts in the same order, used to populate
                TranslationOutput.source.

        Returns:
            Dict with 'output' key containing List[TranslationOutput].
        """
        output_list = []
        for idx, item in enumerate(response_items):
            target_text = item.get("target", "")
            if isinstance(target_text, bytes):
                # Triton BYTES tensors can arrive as raw bytes — decode to string
                target_text = target_text.decode("utf-8")
            source_text = source_texts[idx] if source_texts and idx < len(source_texts) else ""
            from models.schemas.nmt import TranslationOutput
            output_list.append(TranslationOutput(source=source_text, target=target_text))

        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}
