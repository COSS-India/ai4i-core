"""Image task-specific service implementations."""

import json
import logging
from typing import Any, Dict, List, Optional

from services.base.image_base import ImageBase
from models.schemas.ocr import (
    OCRInferenceRequest,
    OCRInferenceResponse,
    OCROutput,
)

logger = logging.getLogger(__name__)


class OCRTaskService(ImageBase):
    """
    Default OCR service (Surya OCR ensemble).

    Inherits the full image pipeline from ImageBase + BaseTaskService:
      _deserialize_payload   → REQUEST_SCHEMA-driven (base)
      validate_request       → image items present (ImageBase)
      preprocess_input       → resolve base64 per item (ImageBase)
      execute_triton_inference (base, via GenericTritonMapper + adapter_config)
      postprocess_output     → unwrap Surya envelope → wrap OCROutput list
      _build_response        → OCRInferenceResponse
    """

    REQUEST_SCHEMA = OCRInferenceRequest

    def __init__(
        self,
        service_info: Optional[Dict[str, Any]] = None,
        **dependencies: Any,
    ):
        super().__init__(service_info=service_info, **dependencies)
        self.logger = logger

    # ------------------------------------------------------------------
    # Postprocess + response building (Surya-specific)
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], **kwargs: Any
    ) -> Dict[str, Any]:
        """Unwrap Surya envelope → wrap each text in OCROutput.
        Bytes were already decoded to UTF-8 strings by GenericTritonMapper."""
        output_list = [
            OCROutput(text=self._unwrap_surya_envelope(item.get("text", "")))
            for item in response_items
        ]
        return {"output": output_list}

    def _build_response(
        self,
        request: OCRInferenceRequest,
        postprocessed: Dict[str, Any],
    ) -> OCRInferenceResponse:
        return OCRInferenceResponse(output=postprocessed["output"])

    def _unwrap_surya_envelope(self, raw_text: Any) -> str:
        """
        Surya ensembles return a JSON envelope per image with a 'full_text' field.
        Unwrap when present; return the value as-is otherwise.
        """
        text = self._decode_text(raw_text)
        if text.lstrip().startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict) and "full_text" in parsed:
                    return str(parsed.get("full_text", ""))
            except json.JSONDecodeError:
                pass
        return text
