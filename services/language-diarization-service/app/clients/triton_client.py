"""Language-Diarization-specific Triton client extending shared base."""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype

from ai4icore_model_management import TritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)


class LanguageDiarizationTritonClient(TritonClient):
    """Triton client with Language-Diarization-specific I/O preparation."""

    def __init__(self, triton_url: str, api_key: Optional[str] = None, timeout: float = 300.0):
        super().__init__(triton_url, api_key=api_key)
        self.timeout = timeout

    def get_language_diarization_io_for_triton(
        self, audio_base64: str, target_language: str = ""
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """Prepare inputs and outputs for language diarization inference.

        Args:
            audio_base64: Base64-encoded audio string
            target_language: Target language code (default: "" for all languages)

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        # Shape [1, 1] for Triton (batch_size=1, num_elements=1)
        inputs = [
            self._get_string_tensor_2d([[audio_base64]], "AUDIO_DATA"),
            self._get_string_tensor_2d([[target_language]], "LANGUAGE"),
        ]
        outputs = [http_client.InferRequestedOutput("DIARIZATION_RESULT")]
        return inputs, outputs

    def run_language_diarization_inference(
        self, audio_base64: str, target_language: str = ""
    ) -> Dict:
        """Run language diarization on a single base64-encoded audio.

        Returns a parsed JSON object from the diarization model.
        If the result cannot be parsed, an empty dict is returned.
        """
        if not audio_base64:
            return {}

        inputs, outputs = self.get_language_diarization_io_for_triton(
            audio_base64, target_language
        )

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.infer(
                model_name="lang_diarization",
                model_version="1",
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except Exception as exc:
            logger.error(
                "Triton Language Diarization inference failed: %s", exc, exc_info=True
            )
            raise TritonInferenceError(
                f"Triton Language Diarization inference failed: {exc}"
            ) from exc

        result = response.as_numpy("DIARIZATION_RESULT")
        if result is None or len(result) == 0:
            logger.warning("Empty response from Triton for language diarization")
            return {}

        # Decode the response -- Result shape is [1, 1], so access [0][0]
        try:
            result_bytes = result[0][0]
        except Exception:
            logger.warning("Failed to extract result from Triton response")
            return {}

        if isinstance(result_bytes, bytes):
            result_str = result_bytes.decode("utf-8")
        else:
            result_str = str(result_bytes)

        logger.debug(
            "Language Diarization Triton response preview=%s",
            result_str[:200],
        )

        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            logger.exception("Failed to parse Language Diarization JSON from Triton")
            return {}

    # ------------------------------------------------------------------
    # Helper for 2D string tensors
    # ------------------------------------------------------------------
    @staticmethod
    def _get_string_tensor_2d(
        values: List[List[str]], tensor_name: str
    ) -> http_client.InferInput:
        """Create a BYTES/string tensor input with shape [batch, 1]."""
        arr = np.array(values, dtype=object)
        inp = http_client.InferInput(
            tensor_name,
            arr.shape,
            np_to_triton_dtype(arr.dtype),
        )
        inp.set_data_from_numpy(arr)
        return inp
