"""NER (Named Entity Recognition) TaskService."""
from services.base.text_base import (
    TextBase,
    build_word_positions,
    group_bpe_tokens,
    align_tags_to_words,
    build_ner_token_predictions,
)
from services.base.task_service import InferenceContext


class NERTaskService(TextBase):
    """Code-output service: BPE-to-word alignment cannot be a JSON transform, so
    it overrides produce_result and sets result.transformed directly (the base
    build_envelope returns it as-is). The alignment helpers live in text_base."""

    async def produce_result(self, result: InferenceContext) -> InferenceContext:
        """
        Align the model's entity-level predictions onto the original text as
        per-token tags with character offsets (the ULCA NER contract).

        Decoding is adapter_config-driven (OUTPUT_TEXT is_json); the alignment
        helpers are imported from text_base. The result is the final task
        output, set on result.transformed.
        """
        sources = result.source_texts
        raw_values = self._get_mapper().decode(result.raw_triton_outputs).get("OUTPUT_TEXT", [])
        items = []
        for value in raw_values:
            if isinstance(value, str):
                # non-JSON is a client error — same as the old in-code parser.
                raise ValueError(f"NER: model returned non-JSON output: {value[:80]!r}")
            if isinstance(value, dict):
                items.extend(value["output"] if "output" in value else [value])
            elif isinstance(value, list):
                items.extend(value)

        output_list = []
        for idx, item in enumerate(items):
            source = item.get("source") or (sources[idx] if idx < len(sources) else "")
            word_positions = build_word_positions(source)
            groups = group_bpe_tokens(item.get("nerPrediction", []))
            aligned = align_tags_to_words(word_positions, groups, source)
            tokens_raw = build_ner_token_predictions(word_positions, aligned)
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

        result.transformed = {"taskType": "ner", "output": output_list, "config": None}
        return result


__all__ = ["NERTaskService"]
