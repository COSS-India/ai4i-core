"""NMT-specific Triton client extending the shared base."""

from typing import List, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient


class NMTTritonClient(TritonClient):
    """Triton client with NMT-specific I/O preparation."""

    def get_translation_io_for_triton(
        self,
        input_texts: List[str],
        source_lang: str,
        target_lang: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare NMT inputs (INPUT_TEXT, INPUT_LANGUAGE_ID, OUTPUT_LANGUAGE_ID) and outputs (OUTPUT_TEXT)."""
        input_text_tensor = self._get_string_tensor(input_texts, "INPUT_TEXT")
        input_lang_tensor = self._get_string_tensor([source_lang] * len(input_texts), "INPUT_LANGUAGE_ID")
        output_lang_tensor = self._get_string_tensor([target_lang] * len(input_texts), "OUTPUT_LANGUAGE_ID")
        output = InferRequestedOutput("OUTPUT_TEXT")
        return [input_text_tensor, input_lang_tensor, output_lang_tensor], [output]
