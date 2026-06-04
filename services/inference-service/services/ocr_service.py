"""OCR TaskService — image-to-text inference (Surya and compatible models)."""

import json
from typing import Any, Dict, List

from services.base.image_base import ImageBase


class OCRTaskService(ImageBase):
    """
    TaskService for OCR inference.

    Inherits validation, base64 resolution, and adapter_config-driven Triton
    I/O from ImageBase; only the output shaping is OCR-specific.
    """

    async def build_response(
        self,
        payload: Dict[str, Any],
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> Dict[str, Any]:
        """Unwrap Surya envelope → shape as {source: <extracted text>, target: ""}
        (NMT-style source/target pairing; target is empty for OCR), plus the
        request config echoed verbatim. We deliberately do NOT synthesize
        language / textDetection here — those values should come from the model
        (Surya detects language) once the envelope is actually parsed for them.
        Faking defaults would lie about the source.
        Bytes were already decoded to UTF-8 strings by GenericTritonMapper."""
        output_list = [
            {"source": self._unwrap_surya_envelope(item.get("text", "")), "target": ""}
            for item in response_items
        ]
        return {
            "output": output_list,
            "config": payload.get("config"),
        }

    # ------------------------------------------------------------------
    # Surya output decoding
    # ------------------------------------------------------------------

    def _decode_text(self, value: Any) -> str:
        """Decode any output value to a UTF-8 string."""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value is None:
            return ""
        return str(value)

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


__all__ = ["OCRTaskService"]
