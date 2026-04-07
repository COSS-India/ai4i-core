"""NER-specific Triton client extending shared base."""

from typing import List, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient


class NERTritonClient(TritonClient):
    """Triton client with NER-specific I/O preparation."""

    def get_ner_io_for_triton(
        self,
        input_texts: List[str],
        language: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare NER inputs (INPUT_TEXT + LANG_ID) and outputs (OUTPUT_TEXT)."""
        input_text_tensor = self._get_string_tensor(input_texts, "INPUT_TEXT")
        lang_tensor = self._get_string_tensor([language] * len(input_texts), "LANG_ID")
        output = InferRequestedOutput("OUTPUT_TEXT")
        return [input_text_tensor, lang_tensor], [output]
