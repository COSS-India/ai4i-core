"""Image task-specific service implementations."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from services.base.image_base import ImageBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.ocr import (
    ImageInput,
    OCRConfig,
    OCRInferenceRequest,
    OCRInferenceResponse,
    OCROutput,
)

logger = logging.getLogger(__name__)


class OCRTaskService(ImageBase):
    """
    Default OCR service (Surya OCR ensemble).

    Inherits the full image pipeline from ImageBase:
      validate_request    → image items present
      preprocess_input    → resolve base64 per item
      execute_triton_inference (ImageBase) → single batched Triton call
      postprocess_output  → unwrap Surya envelope → wrap OCROutput list
      _build_response     → OCRInferenceResponse

    Tensor I/O is mapper-driven via adapter_config sourced from MMS.
    """

    def __init__(
        self,
        service_info: Optional[Dict[str, Any]] = None,
        **dependencies: Any,
    ):
        super().__init__(service_info=service_info, **dependencies)
        self.logger = logger

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> OCRInferenceRequest:
        """Build OCRInferenceRequest from the raw payload dict."""
        try:
            image_items = payload.get("image", [])
            if isinstance(image_items, list) and image_items and isinstance(image_items[0], dict):
                image_items = [ImageInput(**item) for item in image_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = OCRConfig(**config_data)

            return OCRInferenceRequest(image=image_items, config=config_data)
        except Exception as e:
            raise ValueError(f"OCR: failed to deserialize payload: {e}") from e

    # ------------------------------------------------------------------
    # Mapper hooks
    # ------------------------------------------------------------------

    async def convert_payload_to_triton_format(
        self,
        input_data: List[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Render adapter_config inputs against the per-item image context."""
        mapper = GenericTritonMapper(self._adapter_config)
        return mapper.compose_triton_kserve_v2_payload(
            input_data=input_data,
            config=config,
            context_builder=self._build_image_context,
        )

    async def convert_triton_output_to_task_format(
        self,
        triton_output: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Map raw Triton output to a list of {text: ...} dicts via adapter_config."""
        mapper = GenericTritonMapper(self._adapter_config)
        mapped = mapper.map_outputs(triton_output)
        return mapper.to_output_items(mapped)

    def _build_image_context(
        self,
        item: Dict[str, Any],
        index: int,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Expose the current item under `image.*` for value_path declarations."""
        del index, config  # unused; standard per-item context is enough
        return {"image": item}

    # ------------------------------------------------------------------
    # Postprocess + response building
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Decode BYTES → unwrap Surya envelope → wrap each text in OCROutput."""
        decoded = await self._decode_output_bytes(response_items)
        output_list = [
            OCROutput(text=self._unwrap_surya_envelope(item.get("text", "")))
            for item in decoded
        ]
        return {"output": output_list}

    def _build_response(
        self,
        request: OCRInferenceRequest,
        postprocessed: Dict[str, Any],
    ) -> OCRInferenceResponse:
        return OCRInferenceResponse(output=postprocessed["output"])

    # ------------------------------------------------------------------
    # Surya envelope unwrap (OCR-specific)
    # ------------------------------------------------------------------

    def _unwrap_surya_envelope(self, raw_text: Any) -> str:
        """
        Surya ensembles return a JSON envelope per image with a 'full_text' field.
        Unwrap when present; return the value as-is otherwise.
        """
        text = self._decode_text(raw_text)
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "full_text" in parsed:
                    return str(parsed.get("full_text", ""))
            except json.JSONDecodeError:
                pass
        return text
