"""NER (Named Entity Recognition) TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat


class NERTaskService(TextBase):
    # source_language check handled by base; no target language needed

    async def postprocess_output(self, result: PostProcessFormat):
        """
        Align the model's entity-level predictions onto the original text as
        per-token tags with character offsets (the ULCA NER contract).

        JSON parsing is adapter_config-driven (transform "json_parse" on
        OUTPUT_TEXT) — each response item carries the parsed prediction
        object; only the alignment algorithm lives here.
        """
        sources = result.source_texts
        # One parsed JSON document per batch row; a model may wrap multiple
        # results in {"output": [...]}.
        items = []
        for raw_item in result.response_data:
            value = raw_item.get("target")
            if isinstance(value, str):
                # json_parse passes non-JSON through unchanged — same client
                # error the old in-code parser rejected.
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
                    **({"score": t["score"]} if "score" in t else {}),
                }
                for t_idx, t in enumerate(tokens_raw)
            ]
            output_list.append({"source": source, "nerPrediction": ner_predictions})
        self.logger.debug(f"NER post-processed {len(output_list)} predictions")
        return {"taskType": "ner", "output": output_list, "config": None}

    # ------------------------------------------------------------------
    # BPE-to-word alignment helpers
    # ------------------------------------------------------------------

    def _entity(self, pred): return str(pred.get("entity") or pred.get("token") or "")
    def _tag(self, pred):
        for k in ("class","tag","label","entity_type"):
            v = pred.get(k)
            if v is not None and str(v).strip(): return str(v)
        return "O"

    def _score(self, pred):
        """Raw per-BPE-token confidence (common HF token-classification key),
        or None if the model doesn't emit one — score stays optional/omitted
        end-to-end when absent, per the ULCA contract."""
        v = pred.get("score")
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

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
            scores = [s for s in (self._score(p) for p in preds[i:j]) if s is not None]
            groups.append({
                "tag": self._tag(preds[i]),
                "entity": full,
                "first_char": full[0].lower() if full else "",
                "score": (sum(scores) / len(scores)) if scores else None,
            })
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
        tokens = []
        for idx, wi in enumerate(word_positions):
            grp = aligned.get(idx)
            token = {
                "token": wi["word"],
                "tag": grp["tag"] if grp else "O",
                "tokenIndex": idx,
                "tokenStartIndex": wi["start"],
                "tokenEndIndex": wi["end"],
            }
            if grp and grp.get("score") is not None:
                token["score"] = grp["score"]
            tokens.append(token)
        return tokens


__all__ = ["NERTaskService"]
