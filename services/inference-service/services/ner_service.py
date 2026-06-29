"""NER (Named Entity Recognition) TaskService."""
from services.base.text_base import TextBase, flatten_ner_predictions, align_ner_output
from services.base.task_service import InferenceContext


class NERTaskService(TextBase):
    """Code-output service: BPE-to-word alignment cannot be a JSON transform, so
    it overrides post_process and sets result.transformed directly. Tensor
    decoding happens once in run_inference (result.decoded_tensors); the
    alignment helpers live in text_base."""

    async def post_process(self, result: InferenceContext) -> InferenceContext:
        """Align the model's entity predictions onto the original text as
        per-token tags with char offsets (the ULCA NER contract)."""
        raw_values = result.decoded_tensors.get("OUTPUT_TEXT", [])
        output_list = align_ner_output(flatten_ner_predictions(raw_values), result.source_texts)
        result.transformed = {"taskType": "ner", "output": output_list, "config": None}
        return result


__all__ = ["NERTaskService"]
