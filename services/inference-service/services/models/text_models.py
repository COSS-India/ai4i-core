"""Text task service models — NMT (and stubs for NER/Transliteration)."""

from typing import Any, Dict, List

from inference_models.nmt_inference_model import NMTInferenceModel
from models.schemas.nmt import (
    NMTConfig,
    NMTInferenceRequest,
    NMTInferenceResponse,
    TextInput,
    TranslationOutput,
)
from services.base.text_base import TextBase


class TextDefaultModel(TextBase):
    """NMT (Neural Machine Translation) task service."""

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    # async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
    #     """Parse raw dict to typed NMTInferenceRequest.

    #     Accepts both camelCase (portal) and snake_case field names because
    #     all schema models are built with ConfigDict(populate_by_name=True).
    #     """
    #     input_items = [
    #         TextInput(**item) if isinstance(item, dict) else item
    #         for item in payload.get("input", [])
    #     ]
    #     config_data = NMTConfig(**payload.get("config", {}))
    #     return NMTInferenceRequest(input=input_items, config=config_data)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    # async def validate_request(self, request: NMTInferenceRequest) -> None:
    #     await super().validate_request(request)

    #     lang = request.config.language
    #     if not lang.source_language:
    #         raise ValueError(f"{self.task_name}: source_language is required")
    #     if not lang.target_language:
    #         raise ValueError(f"{self.task_name}: target_language is required")
    #     if lang.source_language == lang.target_language:
    #         raise ValueError(
    #             f"{self.task_name}: source_language and target_language must differ "
    #             f"(got '{lang.source_language}')"
    #         )

    # ------------------------------------------------------------------
    # Preprocessing — delegates to TextBase (sanitize + chunk)
    # ------------------------------------------------------------------

    # async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
    #     return await super().preprocess_input(input_data)

    # ------------------------------------------------------------------
    # InferenceModel hook
    # ------------------------------------------------------------------

    # def _create_inference_model(self, adapter_config: Any) -> NMTInferenceModel:
    #     return NMTInferenceModel(adapter_config=adapter_config)

    # ------------------------------------------------------------------
    # Postprocessing
    # ------------------------------------------------------------------

    async def postprocess_output(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: List[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Pair mapper output items with source texts and wrap in TranslationOutput.

        Expects each response_item to have a 'target' key matching the adapter
        config's maps_to declaration for the translated-text output tensor.
        """
        paired = self._pair_with_sources(response_items, source_texts or [])
        output = [
            TranslationOutput(
                source=item.get("source", ""),
                target=item.get("target", ""),
            )
            for item in paired
        ]
        return {"output": output}

    # ------------------------------------------------------------------
    # Response wrapping
    # ------------------------------------------------------------------

    # def _build_response(
    #     self,
    #     request: NMTInferenceRequest,
    #     postprocessed: Dict[str, Any],
    # ) -> NMTInferenceResponse:
    #     return NMTInferenceResponse(output=postprocessed["output"])
