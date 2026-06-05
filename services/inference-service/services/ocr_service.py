"""OCR TaskService — image-to-text inference (Surya and compatible models)."""

from typing import Any, Dict

from services.base.image_base import ImageBase
from services.base.task_service import PostProcessFormat


class OCRTaskService(ImageBase):
    """
    TaskService for OCR inference.

    Inherits validation, base64 resolution, and adapter_config-driven Triton
    I/O from ImageBase; only the output shaping is OCR-specific.
    """

    async def postprocess_output(self, result: PostProcessFormat) -> Dict[str, Any]:
        """Shape as {source: <extracted text>, target: ""} (NMT-style pairing;
        target is empty for OCR) + echo the request config.

        Surya's JSON envelope is unwrapped by the mapper via the adapter
        config's json_field declaration (outputs[].json_field = "full_text"),
        not here."""
        output_list = [
            {"source": self.unwrap_output_value(item.get("text", "")), "target": ""}
            for item in result.response_data
        ]
        return {
            "output": output_list,
            "config": result.payload.get("config"),
        }


__all__ = ["OCRTaskService"]
