"""Text-based TaskService implementations: NMT, NER, Transliteration, LanguageDetection."""

import json
import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.nmt import NMTInferenceResponse
from models.schemas.ner import NERInferenceResponse, NEROutput, Token
from models.schemas.language_detection import (
    LanguageDetectionInferenceResponse,
    LanguageDetectionOutput,
    LanguagePrediction,
)
from models.schemas.transliteration import TransliterationInferenceResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NMT
# ---------------------------------------------------------------------------

class NMTTaskService(TextBase):
    """TaskService for Neural Machine Translation inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.triton_client = None
        self.logger = logger

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)

        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")
        target_lang = language.get("target_language") or language.get("targetLanguage")

        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")
        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(f"NMT: {source_lang} -> {target_lang} ({len(payload.get('input', []))} inputs)")

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    def _build_response(self, payload: Dict[str, Any], postprocessed: Dict[str, Any]) -> NMTInferenceResponse:
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        from models.schemas.nmt import TranslationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            output_list.append(TranslationOutput(source=item["source"], target=item.get("target", "")))
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}


# ---------------------------------------------------------------------------
# NER
# ---------------------------------------------------------------------------

class NERTaskService(TextBase):
    """TaskService for Named Entity Recognition inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)

        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")

        if not source_lang:
            raise ValueError("NER: source_language is required in config.language")

        self.logger.info(f"NER: language={source_lang} ({len(payload.get('input', []))} inputs)")

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        sources = source_texts or []
        raw_items = response_items if isinstance(response_items, list) else [response_items]

        # Step 1 — extract nerPrediction from each mapper item, unwrap scalar nesting,
        # then normalize and join to form the full JSON string
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

        # Step 2 — parse JSON → List[{source, nerPrediction}]
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

    def _build_response(self, payload: Dict[str, Any], postprocessed: Dict[str, Any]) -> NERInferenceResponse:
        return NERInferenceResponse(output=postprocessed["output"])

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
                {
                    "word": word,
                    "start": word_start,
                    "end": word_start + len(word),
                }
            )
            pos = word_start + len(word)
        return word_positions

    def _merge_bpe_entity_text(self, ner_predictions_raw: List[Dict[str, Any]], start: int, end: int) -> str:
        """Merge WordPiece tokens (e.g. ra + ##hul gandhi → rahul gandhi)."""
        parts: List[str] = []
        for idx in range(start, end):
            piece = self._prediction_entity(ner_predictions_raw[idx])
            if piece.startswith("##"):
                parts.append(piece[2:])
            else:
                parts.append(piece)
        if not parts:
            return ""
        merged = parts[0]
        for piece in parts[1:]:
            merged += piece
        return merged.strip()

    def group_bpe_tokens(self, ner_predictions_raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        """
        Map merged entity spans onto whitespace-split words.

        Triton returns lowercase BPE fragments (ra, ##hul gandhi, delhi) while source
        text may be capitalized — match via case-insensitive span overlap in source.
        """
        word_to_pred: Dict[int, Dict[str, Any]] = {}
        source_lower = source.lower()

        for pred_group in groups:
            entity = (pred_group.get("entity") or "").strip()
            if not entity:
                continue
            entity_lower = entity.lower()

            # Find ALL occurrences of the entity span in source (fixes duplicate entity issue)
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

            # Fallback: exact word match only (prevents "in" matching every word with "in")
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
            if word_idx in aligned:
                assigned_tag = aligned[word_idx]["tag"]
            else:
                assigned_tag = "O"

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


# ---------------------------------------------------------------------------
# Transliteration
# ---------------------------------------------------------------------------

class TransliterationTaskService(TextBase):
    """TaskService for Transliteration inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)

        language = payload.get("config", {}).get("language", {})
        source_lang = language.get("source_language") or language.get("sourceLanguage")
        target_lang = language.get("target_language") or language.get("targetLanguage")

        if not source_lang or not target_lang:
            raise ValueError("Transliteration: source_language and target_language are required")
        if source_lang == target_lang:
            raise ValueError("Transliteration: source_language and target_language cannot be the same")

        config = payload.get("config", {})
        num_suggestions = config.get("num_suggestions") or config.get("numSuggestions") or 0
        is_sentence = config.get("is_sentence") or config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError(
                "Transliteration: numSuggestions is not valid for sentence-level transliteration"
            )

        self.logger.info(
            f"Transliteration: {source_lang} -> {target_lang} "
            f"(sentence={is_sentence}, top_k={num_suggestions}, "
            f"{len(payload.get('input', []))} inputs)"
        )

    def _build_response(
        self,
        payload: Dict[str, Any],
        postprocessed: Dict[str, Any],
    ) -> TransliterationInferenceResponse:
        return TransliterationInferenceResponse(output=postprocessed["output"])

    async def postprocess_output(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from models.schemas.transliteration import TransliterationOutput

        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target_raw = item.get("target", "")
            target_text = target_raw[0] if isinstance(target_raw, list) else (target_raw or "")
            output_list.append(
                TransliterationOutput(source=item["source"], target=target_text)
            )

        self.logger.debug(f"Transliteration post-processed {len(output_list)} results")
        return {"output": output_list}


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------

class LanguageDetectionTaskService(TextBase):
    """TaskService for Language Detection inference."""

    def __init__(self, service_info: Optional[Dict[str, Any]] = None, **dependencies: Any):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    async def validate_request(self, payload: Dict[str, Any]) -> None:
        await super().validate_request(payload)
        if not payload.get("input"):
            raise ValueError("LANGUAGE_DETECTION: input array cannot be empty")
        self.logger.info(f"LANGUAGE_DETECTION: {len(payload.get('input', []))} inputs")

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        import math

        output_list = []

        # response_items is a list of dicts — one per input text
        # GenericTritonMapper already extracted OUTPUT_TEXT → mapped to "langPrediction"
        items = response_items if isinstance(response_items, list) else [response_items]

        for item in items:
            # Step 1 — extract the mapped value (JSON string from mapper output)
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            decoded = str(raw_value).strip()

            # Step 2 — parse JSON row {"input": "...", "langCode": "mai_Deva", "confidence": 0.998}
            detection_data = self._parse_detection_row(decoded)

            # Step 3 — split langCode (e.g. "hin_Deva" → lang="hin", script="Deva")
            lang_code_full = detection_data.get("langCode", "other")
            raw_confidence = float(detection_data.get("confidence", 0.0))

            if "_" in lang_code_full:
                lang_code, script_code = lang_code_full.split("_", 1)
            else:
                lang_code, script_code = lang_code_full, None

            # Step 4 — normalize confidence: [0,1] passes through, else sigmoid
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

    def _parse_detection_row(self, decoded_str: str) -> Dict[str, Any]:
        """Parse IndicLID output row. Handles JSON and Python dict repr (single quotes)."""
        import json, ast
        decoded_str = decoded_str.strip()
        try:
            return json.loads(decoded_str)
        except json.JSONDecodeError:
            return ast.literal_eval(decoded_str)

    def _build_response(
        self, payload: Dict[str, Any], postprocessed: Dict[str, Any]
    ) -> LanguageDetectionInferenceResponse:
        return LanguageDetectionInferenceResponse(output=postprocessed["output"])
