"""OCR TaskService — Optical Character Recognition inference (Surya OCR)."""

import logging
from typing import Any, Dict, List, Optional

from services.base.image_base import ImageBase
from models.schemas.ocr import OCRInferenceResponse, OCROutput

logger = logging.getLogger(__name__)


class OCRTaskService(ImageBase):
    """
    Default OCR service (Surya OCR ensemble).

    Inherits the image pipeline from ImageBase + BaseTaskService:
      validate_request       → image items present (ImageBase)
      preprocess_input       → resolve base64 per item (ImageBase)
      execute_triton_inference (base, via GenericTritonMapper + adapter_config)
      postprocess_output     → unwrap Surya envelope → wrap OCROutput list
      _build_response        → OCRInferenceResponse
    """

    def __init__(
        self,
        service_info: Optional[Dict[str, Any]] = None,
        **dependencies: Any,
    ):
        super().__init__(service_info=service_info, **dependencies)
        self.logger = logger
