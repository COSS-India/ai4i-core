"""Speaker Diarization-specific Triton client extending shared base."""

import json
import logging
from typing import Dict, List, Optional, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)


class SpeakerDiarizationTritonClient(TritonClient):
    """Triton client with Speaker Diarization-specific I/O preparation."""

    def get_speaker_diarization_io_for_triton(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """
        Prepare inputs and outputs for speaker diarization inference.

        Args:
            audio_base64: Base64-encoded audio string
            num_speakers: Optional number of speakers (if None, will be auto-detected)

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        num_speakers_str = str(num_speakers) if num_speakers is not None else ""

        audio_tensor = self._get_string_tensor([audio_base64], "AUDIO_DATA")
        speakers_tensor = self._get_string_tensor([num_speakers_str], "NUM_SPEAKERS")

        outputs = [InferRequestedOutput("DIARIZATION_RESULT")]
        return [audio_tensor, speakers_tensor], outputs

    def run_speaker_diarization_inference(
        self, audio_base64: str, num_speakers: Optional[int], model_name: str
    ) -> Dict:
        """
        Run speaker diarization on a single base64-encoded audio.

        Returns a parsed JSON object from the diarization model.
        If the result cannot be parsed, an empty dict is returned.
        """
        if not audio_base64:
            return {}

        inputs, outputs = self.get_speaker_diarization_io_for_triton(audio_base64, num_speakers)
        response = self.send_triton_request(model_name=model_name, inputs=inputs, outputs=outputs)

        result = response.as_numpy("DIARIZATION_RESULT")
        if result is None or len(result) == 0:
            logger.warning("Empty response from Triton for speaker diarization")
            return {}

        # Decode the response - Result shape is [1, 1], so access [0][0]
        try:
            result_bytes = result[0][0]
        except Exception:
            logger.warning("Failed to extract result from Triton response")
            return {}

        result_str = (
            result_bytes.decode("utf-8")
            if isinstance(result_bytes, bytes)
            else str(result_bytes)
        )

        logger.debug("Speaker Diarization Triton response preview=%s", result_str[:200])

        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            logger.exception("Failed to parse Speaker Diarization JSON from Triton")
            return {}
