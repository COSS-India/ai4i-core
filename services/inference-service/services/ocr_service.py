"""OCR TaskService — image-to-text inference (Surya and compatible models)."""

from services.base.image_base import ImageBase


class OCRTaskService(ImageBase):
    """
    TaskService for OCR inference.

    Fully adapter_config-driven: ImageBase handles validation and base64
    resolution; the mapper unwraps Surya's JSON envelope (json_field =
    "full_text"), renames it to output[].source (response_key), and adds
    the constant empty target (response.static_item_fields). The base
    default postprocess_output applies that shaping — no code here.
    """


__all__ = ["OCRTaskService"]
