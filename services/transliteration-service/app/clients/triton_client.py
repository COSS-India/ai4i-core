"""Transliteration-specific Triton client extending shared base."""

import logging
from typing import List, Tuple

import numpy as np
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype

from ai4icore_model_management import TritonClient

logger = logging.getLogger(__name__)


class TransliterationTritonClient(TritonClient):
    """Triton client with transliteration-specific I/O preparation."""

    @staticmethod
    def _flat_string_tensor(values: List[str], name: str) -> InferInput:
        """Create a string tensor with shape [batch] (flat) as required by the transliteration model."""
        np_array = np.array(values, dtype=object)
        tensor = InferInput(name, list(np_array.shape), np_to_triton_dtype(np_array.dtype))
        tensor.set_data_from_numpy(np_array)
        return tensor

    def get_transliteration_io_for_triton(
        self,
        input_texts: List[str],
        source_lang: str,
        target_lang: str,
        is_word_level: bool,
        top_k: int = 0,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare transliteration inputs and outputs for Triton inference."""
        input_text_tensor = self._flat_string_tensor(input_texts, "INPUT_TEXT")
        input_lang_tensor = self._flat_string_tensor(
            [source_lang] * len(input_texts), "INPUT_LANGUAGE_ID"
        )
        output_lang_tensor = self._flat_string_tensor(
            [target_lang] * len(input_texts), "OUTPUT_LANGUAGE_ID"
        )

        # IS_WORD_LEVEL (BOOL)
        is_word_array = np.array([is_word_level] * len(input_texts), dtype=bool)
        is_word_tensor = InferInput(
            "IS_WORD_LEVEL",
            is_word_array.shape,
            np_to_triton_dtype(is_word_array.dtype),
        )
        is_word_tensor.set_data_from_numpy(is_word_array)

        # TOP_K (UINT8)
        top_k_array = np.array([top_k] * len(input_texts), dtype=np.uint8)
        top_k_tensor = InferInput(
            "TOP_K",
            top_k_array.shape,
            np_to_triton_dtype(top_k_array.dtype),
        )
        top_k_tensor.set_data_from_numpy(top_k_array)

        output = InferRequestedOutput("OUTPUT_TEXT")

        inputs = [
            input_text_tensor,
            input_lang_tensor,
            output_lang_tensor,
            is_word_tensor,
            top_k_tensor,
        ]
        outputs = [output]

        return inputs, outputs
