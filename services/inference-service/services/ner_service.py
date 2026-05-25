"""NER (Named Entity Recognition) TaskService."""
import json, logging
from typing import Any, Dict, List, Optional
from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.ner import NERInferenceResponse, NEROutput, Token
logger = logging.getLogger(__name__)

class NERTaskService(TextBase):
    # source_language check handled by base; no target language needed

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    async def postprocess_output(self, response_items, source_texts=None):
        sources = source_texts or []
        raw_items = response_items if isinstance(response_items, list) else [response_items]
        json_parts = []
        for raw_item in raw_items:
            value = GenericTritonMapper.unwrap_scalar(
                raw_item.get("target", raw_item.get("nerPrediction", "")) if isinstance(raw_item, dict) else raw_item
            )
            text = self._norm_json_str(value if isinstance(value, str) else str(value))
            if text:
                json_parts.append(text)
        decoded = json_parts[0] if len(json_parts) == 1 else "".join(json_parts)
        items = self._parse_ner_json(decoded)
        output_list = []
        for idx, item in enumerate(items):
            source = item.get("source") or (sources[idx] if idx < len(sources) else "")
            word_positions = self._build_word_positions(source)
            ner_raw = item.get("nerPrediction", [])
            groups = self._group_bpe_tokens(ner_raw)
            aligned = self._align_tags_to_words(word_positions, groups, source)
            tokens_raw = self._build_ner_token_predictions(word_positions, aligned)
            tokens = [Token(text=t["token"], entity_type=t["tag"], start_pos=t["tokenStartIndex"], end_pos=t["tokenEndIndex"]) for t in tokens_raw]
            output_list.append(NEROutput(source=source, tokens=tokens))
        self.logger.debug(f"NER post-processed {len(output_list)} predictions")
        return {"output": output_list}

    def _build_response(self, payload, postprocessed):
        return NERInferenceResponse(output=postprocessed["output"])

__all__ = ["NERTaskService"]
