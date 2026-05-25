"""NER (Named Entity Recognition) TaskService."""

import json
import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.ner import NERInferenceResponse, NEROutput, Token

logger = logging.getLogger(__name__)


class NERTaskService(TextBase):
    """TaskService for Named Entity Recognition inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **kwargs: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)

        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")

        if not source_lang:
            raise ValueError("NER: source_language is required in config.language")

        self.logger.info(f"NER: language={source_lang} ({len(payload.get('input', []))} inputs)")

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        sources = source_texts or []
        raw_items = response_items if isinstance(response_items, list) else [response_items]

        json_parts = []
        for raw_item in raw_items:
            value = GenericTritonMapper.unwrap_scalar(
                raw_item.get("nerPrediction", "") if isinstance(raw_item, dict) else raw_item
            )
            text = self._normalize_decoded_json_string(
                value if isinstance(value, str) else str(value)
            )
            if text:
                json_parts.append(text)

        decoded = json_parts[0] if len(json_parts) == 1 else "".join(json_parts)
        items = self.parse_ner_json(decoded)

        output_list = []
        for idx, item in enumerate(items):
            source = item.get("source") or (sources[idx] if idx < len(sources) else "")

            word_positions = self.build_word_positions(source)
            ner_raw = item.get("nerPrediction", [])

            if not ner_raw:
                self.logger.warning(
                    "NER: Triton returned empty nerPrediction for source=%r; "
                    "all tokens will be tagged O",
                    source[:80],
                )

            groups = self.group_bpe_tokens(ner_raw)
            aligned = self.align_tags_to_words(word_positions, groups, source)
            tokens_raw = self.build_ner_token_predictions(word_positions, aligned)

            tokens = [
                Token(
                    text=t["token"],
                    entity_type=t["tag"],
                    start_pos=t["tokenStartIndex"],
                    end_pos=t["tokenEndIndex"],
                )
                for t in tokens_raw
            ]
            output_list.append(NEROutput(source=source, tokens=tokens))

        self.logger.debug(f"NER post-processed {len(output_list)} predictions")
        return {"output": output_list}

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> NERInferenceResponse:
        return NERInferenceResponse(output=postprocessed["output"])

    # ------------------------------------------------------------------
    # NER-specific helpers
    # ------------------------------------------------------------------

    def _prediction_entity(self, pred: Dict[str, Any]) -> str:
        entity = pred.get("entity") or pred.get("token") or ""
        return entity if isinstance(entity, str) else str(entity)

    def _prediction_tag(self, pred: Dict[str, Any]) -> str:
        for key in ("class", "tag", "label", "entity_type"):
            tag = pred.get(key)
            if tag is not None and str(tag).strip():
                return str(tag)
        return "O"

    def _normalize_decoded_json_string(self, decoded: str) -> str:
        decoded = decoded.strip()
        if decoded.startswith("[b'") and decoded.endswith("']"):
            decoded = decoded[3:-2]
        elif decoded.startswith('[b"') and decoded.endswith('"]'):
            decoded = decoded[3:-2]
        return decoded.replace("\\\\", "\\")

    def parse_ner_json(self, decoded: str) -> List[Dict[str, Any]]:
        """Parse model JSON into a list of {source, nerPrediction} dicts."""
        if not decoded:
            return []
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise ValueError(f"NER: Failed to parse model output JSON: {exc}") from exc

        if isinstance(parsed, dict) and "output" in parsed:
            raw_output = parsed["output"]
        elif isinstance(parsed, dict):
            raw_output = [parsed]
        else:
            raw_output = parsed if isinstance(parsed, list) else [parsed]
        return raw_output

    def build_word_positions(self, source: str) -> List[Dict[str, Any]]:
        """Map each whitespace-delimited word to character start/end offsets."""
        word_positions: List[Dict[str, Any]] = []
        pos = 0
        for word in source.split():
            word_start = source.find(word, pos)
            word_positions.append(
                {"word": word, "start": word_start, "end": word_start + len(word)}
            )
            pos = word_start + len(word)
        return word_positions

    def _merge_bpe_entity_text(
        self, ner_predictions_raw: List[Dict[str, Any]], start: int, end: int
    ) -> str:
        """Merge WordPiece tokens (e.g. ra + ##hul → rahul)."""
        parts: List[str] = []
        for idx in range(start, end):
            piece = self._prediction_entity(ner_predictions_raw[idx])
            parts.append(piece[2:] if piece.startswith("##") else piece)
        if not parts:
            return ""
        merged = parts[0]
        for piece in parts[1:]:
            merged += piece
        return merged.strip()

    def group_bpe_tokens(
        self, ner_predictions_raw: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Group BERT-style ## subword tokens into merged entity spans."""
        groups: List[Dict[str, Any]] = []
        i = 0
        while i < len(ner_predictions_raw):
            pred = ner_predictions_raw[i]
            entity = self._prediction_entity(pred)
            tag = self._prediction_tag(pred)

            if not entity:
                i += 1
                continue

            j = i + 1
            while j < len(ner_predictions_raw):
                next_entity = self._prediction_entity(ner_predictions_raw[j])
                if next_entity.startswith("##"):
                    j += 1
                else:
                    break

            full_entity = self._merge_bpe_entity_text(ner_predictions_raw, i, j)
            groups.append(
                {
                    "tag": tag,
                    "entity": full_entity,
                    "first_char": full_entity[0].lower() if full_entity else "",
                }
            )
            i = j
        return groups

    def align_tags_to_words(
        self,
        word_positions: List[Dict[str, Any]],
        groups: List[Dict[str, Any]],
        source: str,
    ) -> Dict[int, Dict[str, Any]]:
        """Map merged entity spans onto whitespace-split words."""
        word_to_pred: Dict[int, Dict[str, Any]] = {}
        source_lower = source.lower()

        for pred_group in groups:
            entity = (pred_group.get("entity") or "").strip()
            if not entity:
                continue
            entity_lower = entity.lower()

            search_pos = 0
            matched = False
            while True:
                span_start = source_lower.find(entity_lower, search_pos)
                if span_start < 0:
                    break
                span_end = span_start + len(entity_lower)
                for word_idx, word_info in enumerate(word_positions):
                    if word_info["start"] < span_end and word_info["end"] > span_start:
                        word_to_pred[word_idx] = pred_group
                matched = True
                search_pos = span_end

            if matched:
                continue

            for word_idx, word_info in enumerate(word_positions):
                if word_info["word"].lower() == entity_lower:
                    word_to_pred[word_idx] = pred_group

        return word_to_pred

    def build_ner_token_predictions(
        self,
        word_positions: List[Dict[str, Any]],
        aligned: Dict[int, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build per-word token predictions with character offsets."""
        token_predictions: List[Dict[str, Any]] = []
        for word_idx, word_info in enumerate(word_positions):
            word = word_info["word"]
            assigned_tag = aligned[word_idx]["tag"] if word_idx in aligned else "O"
            token_predictions.append(
                {
                    "token": word,
                    "tag": assigned_tag,
                    "tokenIndex": word_idx,
                    "tokenStartIndex": word_info["start"],
                    "tokenEndIndex": word_info["end"],
                }
            )
        return token_predictions
