"""TTS-specific Triton client extending the shared base."""

from typing import List, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient


class TTSTritonClient(TritonClient):
    """Triton client with TTS-specific I/O preparation."""

    def get_tts_io_for_triton(
        self,
        text: str,
        gender: str,
        language: str,
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """Prepare TTS inputs (INPUT_TEXT, INPUT_SPEAKER_ID, INPUT_LANGUAGE_ID) and outputs (OUTPUT_GENERATED_AUDIO)."""
        text_tensor = self._get_string_tensor([text], "INPUT_TEXT")
        speaker_tensor = self._get_string_tensor([gender], "INPUT_SPEAKER_ID")
        language_tensor = self._get_string_tensor([language], "INPUT_LANGUAGE_ID")
        output = InferRequestedOutput("OUTPUT_GENERATED_AUDIO")
        return [text_tensor, speaker_tensor, language_tensor], [output]
