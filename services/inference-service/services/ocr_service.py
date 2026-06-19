"""OCR TaskService — image-to-text inference (Surya and compatible models)."""

from typing import Any, Dict, Optional

from services.base.image_base import ImageBase

_SMALL_THRESHOLD = 200
_MEDIUM_THRESHOLD = 1000


class OCRTaskService(ImageBase):
    """
    TaskService for OCR inference.

    Fully adapter_config-driven: ImageBase handles validation and base64
    resolution; the mapper unwraps Surya's JSON envelope (json_field =
    "full_text"), renames it to output[].source (response_key), and adds
    the constant empty target (response.static_item_fields). The base
    default postprocess_output applies that shaping — no code here.
    """

    async def process(
        self,
        payload: Dict[str, Any],
        serviceInfo: Optional[Dict[str, Any]] = None,
    ) -> Any:
        return self._stub_response(payload)

    def _stub_response(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from response_test.responses.ocr_responses import (
            SMALL_OCR_RESPONSE,
            MEDIUM_OCR_RESPONSE,
            LARGE_OCR_RESPONSE,
        )
        image_items = payload.get("image") or []
        total_length = sum(
            len(item.get("imageContent") or item.get("imageUri", ""))
            for item in image_items
        )
        if total_length < _SMALL_THRESHOLD:
            return SMALL_OCR_RESPONSE
        if total_length < _MEDIUM_THRESHOLD:
            return MEDIUM_OCR_RESPONSE
        return LARGE_OCR_RESPONSE


__all__ = ["OCRTaskService"]
