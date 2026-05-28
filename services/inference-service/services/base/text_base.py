"""
TextBase — base class for all text-backed inference services.

Centralised validation:
  - input existence and non-empty
  - source_language (all services with language config)
  - target_language + not-equal (REQUIRES_TARGET_LANGUAGE=True)

Child classes only add service-specific logic on top of super().validate_request().
"""

from typing import Any, Dict, List, Optional
from interfaces.task_service import BaseTaskService
import json, logging


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
