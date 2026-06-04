"""NER (Named Entity Recognition) TaskService."""
import json
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat
from services.base.config_mapper import GenericTritonMapper


class NERTaskService(TextBase):
    # source_language check handled by base; no target language needed

    async def postprocess_output(self, result: PostProcessFormat):
        sources = result.source_texts
        raw_items = result.response_data
        json_parts = []
        for raw_item in raw_items:
            value = GenericTritonMapper.unwrap_scalar(
                raw_item.get("target", raw_item.get("nerPrediction", "")) if isinstance(raw_item, dict) else raw_item
            )
            text = self._norm_json_str(value if isinstance(value, str) else str(value))
            if text:
                json_parts.append(text)
        # Each part is a complete JSON document (one per batch row) — parse
        # individually; concatenating two docs would produce invalid JSON.
        items = []
        for part in json_parts:
            items.extend(self._parse_ner_json(part))
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
        return {"taskType": "ner", "output": output_list, "config": None}

    # ------------------------------------------------------------------
    # NER output parsing + BPE-to-word alignment helpers
    # ------------------------------------------------------------------

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


__all__ = ["NERTaskService"]
