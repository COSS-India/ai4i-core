"""Language Detection TaskService."""

import logging
import math
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from models.schemas.language_detection import (
    LanguageDetectionInferenceResponse,
    LanguageDetectionOutput,
    LanguagePrediction,
)

logger = logging.getLogger(__name__)


class LanguageDetectionTaskService(TextBase):
    """TaskService for Language Detection inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)
        if not payload.get("input"):
            raise ValueError("LANGUAGE_DETECTION: input array cannot be empty")
        self.logger.info(f"LANGUAGE_DETECTION: {len(payload.get('input', []))} inputs")

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        output_list = []
        items = response_items if isinstance(response_items, list) else [response_items]

        for item in items:
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            decoded = str(raw_value).strip()
            detection_data = self._parse_detection_row(decoded)

            lang_code_full = detection_data.get("langCode", "other")
            raw_confidence = float(detection_data.get("confidence", 0.0))

            if "_" in lang_code_full:
                lang_code, script_code = lang_code_full.split("_", 1)
            else:
                lang_code, script_code = lang_code_full, None

            if 0.0 <= raw_confidence <= 1.0:
                confidence = raw_confidence
            else:
                confidence = 1.0 / (1.0 + math.exp(-raw_confidence))

            primary = LanguagePrediction(
                language_code=lang_code,
                language=lang_code,
                script_code=script_code,
                confidence=round(confidence, 6),
            )
            output_list.append(LanguageDetectionOutput(primary_language=primary))

        self.logger.debug(f"LANGUAGE_DETECTION post-processed {len(output_list)} results")
        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> LanguageDetectionInferenceResponse:
        return LanguageDetectionInferenceResponse(output=postprocessed["output"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_detection_row(self, decoded_str: str) -> Dict[str, Any]:
        """Parse IndicLID output row. Handles JSON and Python dict repr (single quotes)."""
        import json, ast
        decoded_str = decoded_str.strip()
        try:
            return json.loads(decoded_str)
        except json.JSONDecodeError:
            return ast.literal_eval(decoded_str)
