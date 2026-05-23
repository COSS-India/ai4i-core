"""Text-based TaskService implementations: NMT, NER, Transliteration, LanguageDetection."""

import json
import logging
from typing import Any, Dict, List, Optional

from services.base.text_base import TextBase
from services.base.config_mapper import GenericTritonMapper
from models.schemas.nmt import NMTInferenceRequest, NMTInferenceResponse
from models.schemas.ner import NERInferenceRequest, NERInferenceResponse, NEROutput, Token
from models.schemas.language_detection import (
    LanguageDetectionInferenceRequest,
    LanguageDetectionInferenceResponse,
    LanguageDetectionOutput,
    LanguagePrediction,
)
from models.schemas.transliteration import (
    TransliterationInferenceRequest,
    TransliterationInferenceResponse,
)

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

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NMTInferenceRequest:
        try:
            from models.schemas.nmt import TextInput, NMTConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = NMTConfig(**config_data)

            return NMTInferenceRequest(input=input_items, config=config_data)
        except Exception as e:
            raise ValueError(f"NMT: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        language = getattr(getattr(request, "config", None), "language", None)
        source_lang = getattr(language, "source_language", None)
        target_lang = getattr(language, "target_language", None)

        if not source_lang or not target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage are required")
        if source_lang == target_lang:
            raise ValueError("NMT: sourceLanguage and targetLanguage cannot be the same")

        self.logger.info(f"NMT: {source_lang} -> {target_lang} ({len(request.input)} inputs)")

    def _get_inference_model_class(self) -> type:
        return GenericTritonMapper

    def _build_response(self, request: NMTInferenceRequest, postprocessed: Dict[str, Any]) -> NMTInferenceResponse:
        return NMTInferenceResponse(output=postprocessed["output"], smr_response=None)

    async def postprocess_output(
        self, response_items: List[Dict[str, Any]], source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        from models.schemas.nmt import TranslationOutput
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target_text = item.get("target", "")
            if isinstance(target_text, bytes):
                target_text = target_text.decode("utf-8")
            output_list.append(TranslationOutput(source=item["source"], target=target_text))
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

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> NERInferenceRequest:
        try:
            from models.schemas.ner import TextInput, NERConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = NERConfig(**config_data)

            return NERInferenceRequest(input=input_items, config=config_data)
        except Exception as e:
            raise ValueError(f"NER: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        language = getattr(getattr(request, "config", None), "language", None)
        source_lang = getattr(language, "source_language", None)

        if not source_lang:
            raise ValueError("NER: source_language is required in config.language")

        self.logger.info(f"NER: language={source_lang} ({len(request.input)} inputs)")

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        # Step 1 — decode raw Triton output → clean JSON string
        decoded = self.decode_triton_output(response_items)

        # Step 2 — parse JSON → List[dict]
        items = self.parse_ner_json(decoded)
        sources = source_texts or []

        output_list = []
        for idx, item in enumerate(items):
            source = item.get("source") or (sources[idx] if idx < len(sources) else "")

            # Step 3 — build word positions with char offsets
            word_positions = self.build_word_positions(source)

            ner_raw = item.get("nerPrediction", [])
            if not ner_raw:
                self.logger.warning(
                    "NER: Triton returned empty nerPrediction for source=%r; "
                    "all tokens will be tagged O",
                    source[:80],
                )

            # Step 4 — group BERT ## BPE subword tokens (sparse entity spans from model)
            groups = self.group_bpe_tokens(ner_raw)

            # Step 5 — align entity spans to whitespace-split words; rest → O
            aligned = self.align_tags_to_words(word_positions, groups, source)

            # Step 6 — build token predictions with offsets
            tokens_raw = self.build_ner_token_predictions(word_positions, aligned)

            # Step 7 — map to NEROutput schema (Token objects)
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

    def _build_response(self, request: NERInferenceRequest, postprocessed: Dict[str, Any]) -> NERInferenceResponse:
        return NERInferenceResponse(output=postprocessed["output"])

    # ------------------------------------------------------------------
    # NER postprocess helpers (aligned with ner-service postprocess flow)
    # ------------------------------------------------------------------

    # maps_to is the adapter slot for the full OUTPUT_TEXT JSON blob, not the inner array
    _NER_OUTPUT_KEYS = (
        "target",
        "output_text",
        "raw_output",
        "output",
        "prediction",
        "ner_output",
        "text",
        "nerPrediction",
    )

    def decode_triton_output(self, response_items: Any) -> str:
        """
        Decode Triton OUTPUT_TEXT into a JSON string.

        Mirrors ner-service: take OUTPUT_TEXT data, unwrap nested [1,1] lists via [0],
        decode bytes, then normalize.
        """
        if isinstance(response_items, dict) and "outputs" in response_items:
            for output in response_items.get("outputs", []):
                if output.get("name") == "OUTPUT_TEXT":
                    return self._normalize_decoded_json_string(
                        self._triton_data_to_string(output.get("data"))
                    )
            return ""

        if isinstance(response_items, str):
            return self._normalize_decoded_json_string(response_items)
        if isinstance(response_items, bytes):
            return self._normalize_decoded_json_string(
                response_items.decode("utf-8", errors="replace")
            )
        if isinstance(response_items, dict):
            return self._normalize_decoded_json_string(
                self._extract_output_text_from_item(response_items)
            )
        if isinstance(response_items, list):
            parts: List[str] = []
            for item in response_items:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, bytes):
                    parts.append(item.decode("utf-8", errors="replace"))
                elif isinstance(item, dict):
                    text = self._extract_output_text_from_item(item)
                    if text:
                        parts.append(text)
            if not parts:
                return ""
            raw = parts[0] if len(parts) == 1 else "".join(parts)
            return self._normalize_decoded_json_string(raw)
        return self._normalize_decoded_json_string(str(response_items))

    def _unwrap_triton_scalar(self, value: Any) -> Any:
        """Unwrap shape [1,1] nesting — same as ner-service encoded_result[0]."""
        while isinstance(value, list) and len(value) == 1:
            value = value[0]
        return value

    def _triton_data_to_string(self, data: Any) -> str:
        data = self._unwrap_triton_scalar(data)
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        if isinstance(data, str):
            return data
        return str(data)

    def _extract_output_text_from_item(self, item: Dict[str, Any]) -> str:
        for key in self._NER_OUTPUT_KEYS:
            if key in item and item[key] is not None:
                return self._triton_data_to_string(item[key])
        for value in item.values():
            if isinstance(value, (str, bytes, list)):
                text = self._triton_data_to_string(value)
                if text:
                    return text
        return ""

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

            span_start = source_lower.find(entity_lower)
            if span_start >= 0:
                span_end = span_start + len(entity_lower)
                for word_idx, word_info in enumerate(word_positions):
                    if word_info["start"] < span_end and word_info["end"] > span_start:
                        word_to_pred[word_idx] = pred_group
                continue

            # Fallback: single-word case-insensitive match
            for word_idx, word_info in enumerate(word_positions):
                word_lower = word_info["word"].lower()
                if word_lower == entity_lower or entity_lower in word_lower or word_lower in entity_lower:
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

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> TransliterationInferenceRequest:
        try:
            from models.schemas.transliteration import TextInput, TransliterationConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = TransliterationConfig(**config_data)

            return TransliterationInferenceRequest(input=input_items, config=config_data)
        except Exception as e:
            raise ValueError(f"Transliteration: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)

        language = getattr(getattr(request, "config", None), "language", None)
        source_lang = getattr(language, "source_language", None)
        target_lang = getattr(language, "target_language", None)

        if not source_lang or not target_lang:
            raise ValueError("Transliteration: source_language and target_language are required")
        if source_lang == target_lang:
            raise ValueError("Transliteration: source_language and target_language cannot be the same")

        config = request.config
        if config.num_suggestions > 0 and config.is_sentence:
            raise ValueError(
                "Transliteration: numSuggestions is not valid for sentence-level transliteration"
            )

        self.logger.info(
            f"Transliteration: {source_lang} -> {target_lang} "
            f"(sentence={config.is_sentence}, top_k={config.num_suggestions}, "
            f"{len(request.input)} inputs)"
        )

    def _build_response(
        self,
        request: TransliterationInferenceRequest,
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
            if isinstance(target_raw, list):
                target_text = target_raw[0] if target_raw else ""
            elif isinstance(target_raw, bytes):
                target_text = target_raw.decode("utf-8")
            else:
                target_text = str(target_raw) if target_raw is not None else ""

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

    async def _deserialize_payload(self, payload: Dict[str, Any]) -> LanguageDetectionInferenceRequest:
        try:
            from models.schemas.language_detection import TextInput, LanguageDetectionConfig

            input_items = payload.get("input", [])
            if isinstance(input_items, list) and input_items:
                if isinstance(input_items[0], dict):
                    input_items = [TextInput(**item) for item in input_items]

            config_data = payload.get("config", {})
            if isinstance(config_data, dict):
                config_data = LanguageDetectionConfig(**config_data)

            return LanguageDetectionInferenceRequest(input=input_items, config=config_data)
        except Exception as e:
            raise ValueError(f"LANGUAGE_DETECTION: Failed to deserialize payload: {str(e)}")

    async def validate_request(self, request: Any) -> None:
        await super().validate_request(request)
        if not request.input:
            raise ValueError("LANGUAGE_DETECTION: input array cannot be empty")
        self.logger.info(f"LANGUAGE_DETECTION: {len(request.input)} inputs")

    async def postprocess_output(
        self, response_items: Any, source_texts: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        import math

        output_list = []

        # response_items is a list of dicts — one per input text
        # GenericTritonMapper already extracted OUTPUT_TEXT → mapped to "langPrediction"
        items = response_items if isinstance(response_items, list) else [response_items]

        for item in items:
            # Step 1 — extract the mapped value (raw JSON string from Triton)
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            if isinstance(raw_value, bytes):
                decoded = raw_value.decode("utf-8")
            else:
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
        self, request: LanguageDetectionInferenceRequest, postprocessed: Dict[str, Any]
    ) -> LanguageDetectionInferenceResponse:
        return LanguageDetectionInferenceResponse(output=postprocessed["output"])
