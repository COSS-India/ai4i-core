"""Transliteration TaskService."""
from services.base.text_base import TextBase
from services.base.task_service import PostProcessFormat


class TransliterationTaskService(TextBase):
    REQUIRES_TARGET_LANGUAGE = True  # enables target_language + not-equal check in base

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

    async def postprocess_output(self, result: PostProcessFormat):
        """
        Group Triton's per-suggestion batch rows back into one output item
        per original input — the ULCA contract (SentencesList) requires
        `target` as an array of suggestions on a single {source, target} item,
        not one row per suggestion.

        Assumes suggestion rows arrive in consecutive per-input blocks
        (input_index * rows_per_item + suggestion_rank) — the standard
        top-k batching convention. Degrades gracefully (never raises) if the
        row count isn't a clean multiple of rows_per_item.
        """
        config = result.payload.get("config") or {}
        rows_per_item = max(int(config.get("top_k") or 0), 1)

        rows = result.response_data
        if len(rows) != len(result.source_texts) * rows_per_item:
            self.logger.debug(
                "Transliteration: unexpected row count (%d rows, %d inputs, %d rows/item)",
                len(rows), len(result.source_texts), rows_per_item,
            )

        output = []
        for idx, source in enumerate(result.source_texts):
            start = idx * rows_per_item
            chunk = rows[start:start + rows_per_item]
            targets = [
                self.unwrap_output_value(row.get("target"))
                for row in chunk if row.get("target") is not None
            ]
            output.append({"source": source, "target": targets})
        return {"output": output}

__all__ = ["TransliterationTaskService"]
