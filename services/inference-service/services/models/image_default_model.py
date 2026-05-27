"""
ImageDefaultModel — shared image model for tasks that send images to Triton.

Used by image tasks where the output needs no task-specific shaping: the mapped
Triton output items are returned as-is and the route layer applies
GenericInferenceResponse. Different tasks share this class; the adapter_config
and Triton model name are what differ.

Base64 resolution (inline imageContent or downloaded imageUri) and Triton I/O
(payload assembly, output mapping via GenericTritonMapper + adapter_config) are
inherited from ImageBase — concrete tasks don't reimplement them.
"""

import logging
from typing import Any, Dict, List, Optional

from services.base.image_base import ImageBase

logger = logging.getLogger(__name__)


class ImageDefaultModel(ImageBase):
    """
    Concrete image model for generic-passthrough tasks.

    Inherits validation, base64 resolution, and adapter_config-driven Triton
    I/O from ImageBase. Output is returned as a generic dict — the route layer
    applies GenericInferenceResponse, so no task-specific subclassing is needed.
    """

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info, **kwargs)
        self.logger = logger

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Unwrap Surya envelope → wrap each text in OCROutput.
        Bytes were already decoded to UTF-8 strings by GenericTritonMapper."""
        output_list = [
            {"text": self._unwrap_surya_envelope(item.get("text", ""))}
            for item in response_items
        ]
        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {"output": postprocessed["output"]}
