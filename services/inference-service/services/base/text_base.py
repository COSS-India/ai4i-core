"""
TextBase — base class for all text-backed inference services.

Centralised validation:
  - input existence and non-empty
  - source_language (all services with language config)
  - target_language + not-equal (REQUIRES_TARGET_LANGUAGE=True)

Concrete text task services live in this module too:
  TextDefaultModel               — NMT (default text model)
  NERTaskService                 — Named Entity Recognition
  LanguageDetectionTaskService   — Language Detection
  TransliterationTaskService     — Transliteration

Child classes only add service-specific logic on top of super().validate_request().
"""

from typing import Any, Dict, List, Optional
from interfaces.task_service import BaseTaskService
from services.base.config_mapper import GenericTritonMapper
import json, logging

logger = logging.getLogger(__name__)


class TextBase(BaseTaskService):
    CHUNK_SIZE: int = 90

    # Set True in subclasses that require both source and target language (NMT, Transliteration)
    REQUIRES_TARGET_LANGUAGE: bool = False

    # ------------------------------------------------------------------
    # Common language helpers
    # ------------------------------------------------------------------

    def _get_language(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return payload.get("config", {}).get("language", {})

    def _extract_source_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("source_language") or language.get("sourceLanguage")

    def _extract_target_lang(self, language: Dict[str, Any]) -> Optional[str]:
        return language.get("target_language") or language.get("targetLanguage")

    # ------------------------------------------------------------------
    # Payload key
    # ------------------------------------------------------------------

    def get_payload_object(self, payload: Dict[str, Any]) -> List[Any]:
        """Text input list lives under payload['input']."""
        return payload.get("input") or []

    # ------------------------------------------------------------------
    # Common validate_request
    # ------------------------------------------------------------------

    async def validate_request(self, payload: Any) -> None:
        await super().validate_request(payload)

        if not payload.get("input"):
            raise ValueError(f"{self.task_name}: payload must contain a non-empty 'input' field")
        if not payload.get("config"):
            raise ValueError(f"{self.task_name}: payload must contain a 'config' field")

        for idx, item in enumerate(payload.get("input", [])):
            source = item.get("source") if isinstance(item, dict) else getattr(item, "source", None)
            if not source or not isinstance(source, str):
                raise ValueError(f"{self.task_name}: input[{idx}]['source'] must be a non-empty string")

        language = self._get_language(payload)
        if language:
            source_lang = self._extract_source_lang(language)
            if not source_lang:
                raise ValueError(f"{self.task_name}: config.language.source_language is required")

            if self.REQUIRES_TARGET_LANGUAGE:
                target_lang = self._extract_target_lang(language)
                if not target_lang:
                    raise ValueError(f"{self.task_name}: config.language.target_language is required")
                if source_lang == target_lang:
                    raise ValueError(f"{self.task_name}: source_language and target_language cannot be the same")

    # ------------------------------------------------------------------
    # preprocess_input
    # ------------------------------------------------------------------

    async def preprocess_input(self, input_data: List[Any]) -> List[Dict[str, Any]]:
        await super().preprocess_input(input_data)

        source_texts = await self.extract_field_from_items(input_data, "source")
        sanitized = [self._sanitize_source(t) for t in source_texts]

        items = []
        for flat_idx, item in enumerate(input_data):
            item_dict = (
                item if isinstance(item, dict)
                else (item.model_dump(by_alias=False) if hasattr(item, "model_dump") else item.dict())
            )
            items.append({
                **item_dict,
                "source": sanitized[flat_idx] if flat_idx < len(sanitized) else "",
                "_chunk": flat_idx // self.CHUNK_SIZE,
            })

        return items

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _sanitize_source(self, text: Any) -> str:
        if not text:
            return " "
        text = str(text).replace("\n", " ").replace("\r", " ")
        return self._normalize_text(text) or " "

    def _chunk_inputs(self, items: List[Any], size: int = 90) -> List[List[Any]]:
        return [items[i: i + size] for i in range(0, len(items), size)]

    def _normalize_text(self, text: str) -> str:
        return " ".join(text.split()).strip()

    def _pair_with_sources(
        self,
        response_items: List[Dict[str, Any]],
        source_texts: List[str],
    ) -> List[Dict[str, Any]]:
        paired = []
        for idx, item in enumerate(response_items):
            source = source_texts[idx] if idx < len(source_texts) else ""
            paired.append({**item, "source": source})
        return paired

    def _norm_json_str(self, s):
        s = s.strip()
        if s.startswith("[b'") and s.endswith("']"): s = s[3:-2]
        elif s.startswith('[b"') and s.endswith('"]'): s = s[3:-2]
        return s.replace("\\\\", "\\")

    def _parse_ner_json(self, decoded):
        if not decoded: return []
        try: parsed = json.loads(decoded)
        except json.JSONDecodeError as e: raise ValueError(f"NER: bad JSON: {e}") from e
        if isinstance(parsed, dict) and "output" in parsed: return parsed["output"]
        if isinstance(parsed, dict): return [parsed]
        return parsed if isinstance(parsed, list) else [parsed]

    def _entity(self, pred): return str(pred.get("entity") or pred.get("token") or "")
    def _tag(self, pred):
        for k in ("class","tag","label","entity_type"):
            v = pred.get(k)
            if v is not None and str(v).strip(): return str(v)
        return "O"

    def _build_word_positions(self, source):
        positions, pos = [], 0
        for word in source.split():
            start = source.find(word, pos)
            positions.append({"word": word, "start": start, "end": start + len(word)})
            pos = start + len(word)
        return positions

    def _merge_bpe(self, preds, start, end):
        parts = []
        for i in range(start, end):
            p = self._entity(preds[i])
            parts.append(p[2:] if p.startswith("##") else p)
        return (parts[0] + "".join(parts[1:])).strip() if parts else ""

    def _group_bpe_tokens(self, preds):
        groups, i = [], 0
        while i < len(preds):
            entity = self._entity(preds[i])
            if not entity: i += 1; continue
            j = i + 1
            while j < len(preds) and self._entity(preds[j]).startswith("##"): j += 1
            full = self._merge_bpe(preds, i, j)
            groups.append({"tag": self._tag(preds[i]), "entity": full, "first_char": full[0].lower() if full else ""})
            i = j
        return groups

    def _align_tags_to_words(self, word_positions, groups, source):
        word_to_pred, src_lower = {}, source.lower()
        for grp in groups:
            entity = (grp.get("entity") or "").strip()
            if not entity: continue
            ent_lower, search_pos, matched = entity.lower(), 0, False
            while True:
                s = src_lower.find(ent_lower, search_pos)
                if s < 0: break
                e = s + len(ent_lower)
                for wi, winfo in enumerate(word_positions):
                    if winfo["start"] < e and winfo["end"] > s: word_to_pred[wi] = grp
                matched = True; search_pos = e
            if matched: continue
            for wi, winfo in enumerate(word_positions):
                if winfo["word"].lower() == ent_lower: word_to_pred[wi] = grp
        return word_to_pred

    def _build_ner_token_predictions(self, word_positions, aligned):
        return [{"token": wi["word"], "tag": aligned[idx]["tag"] if idx in aligned else "O",
                 "tokenIndex": idx, "tokenStartIndex": wi["start"], "tokenEndIndex": wi["end"]}
                for idx, wi in enumerate(word_positions)]

    def _chunk_text(self, text: str, max_length: int = 400) -> List[str]:
        """Split text into chunks ≤ max_length chars at sentence/clause boundaries."""
        text = self._normalize_text(text)
        if not text:
            return [""]
        if len(text) <= max_length:
            return [text]

        chunks: List[str] = []
        while len(text) > max_length:
            split_pos = max_length
            for sep in ('.', '?', '!', '।', ',', ' '):
                pos = text.rfind(sep, 0, max_length)
                if pos > 0:
                    split_pos = pos + 1
                    break
            chunks.append(text[:split_pos].strip())
            text = text[split_pos:].strip()

        if text:
            chunks.append(text)
        return [c for c in chunks if c]


class TextDefaultModel(TextBase):
    """NMT (Neural Machine Translation) TaskService — default text model."""

    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    def _build_response(self, payload, postprocessed):
        return {"output": postprocessed["output"]}

    async def postprocess_output(self, response_items, source_texts=None):
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target = item.get("target", "")
            # Unwrap single-element list nesting from Triton KServe v2 responses
            while isinstance(target, (list, tuple)) and len(target) == 1:
                target = target[0]
            if isinstance(target, bytes):
                target = target.decode("utf-8", errors="replace")
            output_list.append({"source": item["source"], "target": str(target)})
        self.logger.debug(f"NMT post-processed {len(output_list)} translations")
        return {"output": output_list}


class NERTaskService(TextBase):
    """NER (Named Entity Recognition) TaskService."""

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
            ner_predictions = [
                {
                    "token":            t["token"],
                    "tag":              t["tag"],
                    "tokenIndex":       t_idx,
                    "tokenStartIndex":  t["tokenStartIndex"],
                    "tokenEndIndex":    t["tokenEndIndex"],
                }
                for t_idx, t in enumerate(tokens_raw)
            ]
            output_list.append({"source": source, "nerPrediction": ner_predictions})
        self.logger.debug(f"NER post-processed {len(output_list)} predictions")
        return {"output": output_list}

    def _build_response(self, payload, postprocessed):
        return {"taskType": "ner", **postprocessed, "config": None}


class LanguageDetectionTaskService(TextBase):
    """Language Detection TaskService."""

    # No language config required — language is DETECTED not specified
    # Base validate_request handles input existence; language block skipped.

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    async def postprocess_output(self, response_items, source_texts=None):
        """
        Return output items with 'source' (input text) and 'langPrediction'
        as a list of prediction objects: [{langCode, scriptCode, langScore, language}, ...]
        """
        output_list = []
        sources = source_texts or []
        items = response_items if isinstance(response_items, list) else [response_items]
        for idx, item in enumerate(items):
            raw_value = item.get("langPrediction", "") if isinstance(item, dict) else item
            # Unwrap Triton KServe v2 nesting: only peel [bytes] or [string] wrappers
            while isinstance(raw_value, (list, tuple)) and len(raw_value) == 1 and isinstance(raw_value[0], (bytes, str)):
                raw_value = raw_value[0]
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8", errors="replace")
            # Parse JSON-encoded prediction string into a list of prediction objects
            if isinstance(raw_value, str):
                try:
                    raw_value = json.loads(raw_value)
                except (json.JSONDecodeError, ValueError):
                    raw_value = raw_value.strip()
            # Always return langPrediction as a list
            if not isinstance(raw_value, list):
                raw_value = [raw_value] if raw_value else []
            source = sources[idx] if idx < len(sources) else ""
            output_list.append({"source": source, "langPrediction": raw_value})
        self.logger.debug(f"LANGUAGE_DETECTION post-processed {len(output_list)} results")
        return {"output": output_list}

    def _build_response(self, payload, postprocessed):
        return postprocessed


class TransliterationTaskService(TextBase):
    """Transliteration TaskService."""

    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

    def __init__(self, service_info=None, **deps):
        super().__init__(service_info=service_info)
        self.logger = logger

    async def validate_request(self, payload):
        await super().validate_request(payload)  # handles input + source/target language checks

        # --- Transliteration-specific: numSuggestions/isSentence + derived field injection ---
        config = payload.get("config", {})
        num_suggestions = config.get("num_suggestions") or config.get("numSuggestions") or 0
        is_sentence = config.get("is_sentence") or config.get("isSentence") or False

        if num_suggestions > 0 and is_sentence:
            raise ValueError("Transliteration: numSuggestions is not valid for sentence-level transliteration")

        # Inject derived fields so mapper can resolve value_path: request.config.is_word_level/top_k
        config["is_word_level"] = not is_sentence
        config["top_k"] = num_suggestions

        src = self._extract_source_lang(self._get_language(payload))
        tgt = self._extract_target_lang(self._get_language(payload))
        self.logger.info(f"Transliteration: {src} -> {tgt} (sentence={is_sentence}, top_k={num_suggestions}, {len(payload.get('input', []))} inputs)")

    def _build_response(self, payload, postprocessed):
        return {"output": postprocessed["output"]}

    async def postprocess_output(self, response_items, source_texts=None):
        paired = self._pair_with_sources(response_items, source_texts or [])
        output_list = []
        for item in paired:
            target_raw = item.get("target", "")
            target_text = target_raw[0] if isinstance(target_raw, list) else (target_raw or "")
            output_list.append({"source": item["source"], "target": target_text})
        self.logger.debug(f"Transliteration post-processed {len(output_list)} results")
        return {"output": output_list}


__all__ = [
    "TextBase",
    "TextDefaultModel",
    "NERTaskService",
    "LanguageDetectionTaskService",
    "TransliterationTaskService",
]
