"""NER (Named Entity Recognition) TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import InferenceContext


class NERTaskService(TextBase):
    # source_language check handled by base; no target language needed

    async def produce_result(self, result: InferenceContext) -> InferenceContext:
        """
        Align the model's entity-level predictions onto the original text as
        per-token tags with character offsets (the ULCA NER contract).

        JSON parsing is adapter_config-driven (transform "json_parse" on
        OUTPUT_TEXT) — each response item carries the parsed prediction
        object; only the alignment algorithm lives here.
        """
        sources = result.source_texts
        # Parsed prediction objects: the mapper decodes the OUTPUT_TEXT tensor
        # (is_json) to objects. A model may wrap multiple results in
        # {"output": [...]}.
        raw_values = self._get_mapper().decode(result.raw_triton_outputs).get("OUTPUT_TEXT", [])
        items = []
        for value in raw_values:
            if isinstance(value, str):
                # non-JSON passes through unchanged — same client error the old
                # in-code parser rejected.
                raise ValueError(f"NER: model returned non-JSON output: {value[:80]!r}")
            if isinstance(value, dict):
                items.extend(value["output"] if "output" in value else [value])
            elif isinstance(value, list):
                items.extend(value)
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
        result.result_items = output_list
        return result

    def build_envelope(self, result: InferenceContext) -> dict:
        """NER envelope: taskType 'ner', the aligned predictions, no config echo."""
        return {"taskType": "ner", "output": result.result_items, "config": None}

    # ------------------------------------------------------------------
    # BPE-to-word alignment helpers
    # ------------------------------------------------------------------

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
