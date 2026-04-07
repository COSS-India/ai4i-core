"""TTS-specific Triton client extending the shared base."""

from typing import List, Tuple

import numpy as np
from tritonclient.http import InferInput, InferRequestedOutput
from tritonclient.utils import np_to_triton_dtype

from ai4icore_model_management import TritonClient


class TTSTritonClient(TritonClient):
    """Triton client with TTS-specific I/O preparation."""

    @staticmethod
    def _flat_string_tensor(value: str, name: str) -> InferInput:
        """Create a string tensor with shape [1] (flat) as required by the TTS model."""
        np_array = np.array([value], dtype=object)
        tensor = InferInput(name, [1], np_to_triton_dtype(np_array.dtype))
        tensor.set_data_from_numpy(np_array)
        return tensor

    def get_tts_io_for_triton(
        self,
        text: str,
        gender: str,
        language: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare TTS inputs (INPUT_TEXT, INPUT_SPEAKER_ID, INPUT_LANGUAGE_ID) and outputs (OUTPUT_GENERATED_AUDIO)."""
        text_tensor = self._flat_string_tensor(text, "INPUT_TEXT")
        speaker_tensor = self._flat_string_tensor(gender, "INPUT_SPEAKER_ID")
        language_tensor = self._flat_string_tensor(language, "INPUT_LANGUAGE_ID")
        output = InferRequestedOutput("OUTPUT_GENERATED_AUDIO")
        return [text_tensor, speaker_tensor, language_tensor], [output]
