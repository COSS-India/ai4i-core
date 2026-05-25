"""Language Detection TaskService."""
import logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.language_detection import LanguageDetectionInferenceResponse, LanguageDetectionOutput, LanguagePrediction
logger = logging.getLogger(__name__)

class LanguageDetectionTaskService(TextBase):
    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self):
        return GenericTritonMapper

    async def validate_request(self, payload):
        await super().validate_request(payload)
        if not payload.get("input"):
            raise ValueError("LANGUAGE_DETECTION: input array cannot be empty")
        self.logger.info(f"LANGUAGE_DETECTION: {len(payload.get('input', []))} inputs")

    async def postprocess_output(self, response_items, source_texts=None):
        import math
        output_list = []
        items = response_items if isinstance(response_items, list) else [response_items]
        for item in items:
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            decoded = str(raw_value).strip()
            detection_data = self._parse_detection_row(decoded)
            lang_code_full = detection_data.get("langCode", "other")
            raw_confidence = float(detection_data.get("confidence", 0.0))
            lang_code, script_code = (lang_code_full.split("_", 1) if "_" in lang_code_full else (lang_code_full, None))
            confidence = raw_confidence if 0.0 <= raw_confidence <= 1.0 else 1.0 / (1.0 + math.exp(-raw_confidence))
            primary = LanguagePrediction(language_code=lang_code, language=lang_code, script_code=script_code, confidence=round(confidence, 6))
            output_list.append(LanguageDetectionOutput(primary_language=primary))
        self.logger.debug(f"LANGUAGE_DETECTION post-processed {len(output_list)} results")
        return {"output": output_list}

    def _parse_detection_row(self, decoded_str):
        import json, ast
        decoded_str = decoded_str.strip()
        try: return json.loads(decoded_str)
        except json.JSONDecodeError: return ast.literal_eval(decoded_str)

    def _build_response(self, payload, postprocessed):
        return LanguageDetectionInferenceResponse(output=postprocessed["output"])

__all__ = ["LanguageDetectionTaskService"]
