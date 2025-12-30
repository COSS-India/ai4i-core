"""
Triton Inference Server client wrapper for Speaker Diarization.

This client sends base64-encoded audio to a Triton deployment of the
speaker diarization model and parses its JSON output.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype
import httpx

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""

    pass


class TritonClient:
    """Triton Inference Server client for Speaker Diarization operations."""

    def __init__(self, triton_url: str, api_key: Optional[str] = None, timeout: float = 300.0):
        """
        :param triton_url: Triton server URL (host:port or http://host:port).
        :param api_key: Optional Bearer token for Authorization header.
        :param timeout: Request timeout in seconds (default: 300.0).
        """
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[http_client.InferenceServerClient] = None

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize Triton URL to host:port format."""
        url = url.strip()
        if url.startswith("http://"):
            url = url[7:]
        elif url.startswith("https://"):
            url = url[8:]
        return url

    @property
    def client(self) -> http_client.InferenceServerClient:
        """Lazy initialization of Triton HTTP client."""
        if self._client is None:
            logger.info(
                "Initializing Triton client for Speaker Diarization with URL: %s",
                self.triton_url,
            )
            try:
                self._client = http_client.InferenceServerClient(
                    url=self.triton_url,
                    verbose=False,
                )
            except Exception as exc:  # pragma: no cover - connectivity error path
                logger.error(
                    "Failed to initialize Triton client with URL '%s': %s",
                    self.triton_url,
                    exc,
                    exc_info=True,
                )
                raise TritonInferenceError(
                    f"Failed to initialize Triton client: {exc}"
                ) from exc
        return self._client

    def _get_string_tensor(
        self, values: List[List[str]], tensor_name: str
    ) -> http_client.InferInput:
        """
        Create a BYTES/string tensor input.

        values should be a nested list shaped like [[value1], [value2], ...]
        so that the final shape is [batch_size, 1].
        """
        arr = np.array(values, dtype=object)
        inp = http_client.InferInput(
            tensor_name,
            arr.shape,
            np_to_triton_dtype(arr.dtype),
        )
        inp.set_data_from_numpy(arr)
        return inp

    def get_speaker_diarization_io_for_triton(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """
        Prepare inputs and outputs for speaker diarization inference.

        Args:
            audio_base64: Base64-encoded audio string
            num_speakers: Optional number of speakers (if None, will be auto-detected)

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        # Shape needs to be [1, 1] for Triton (batch_size=1, num_elements=1)
        # NUM_SPEAKERS is expected as a string in BYTES format
        num_speakers_str = str(num_speakers) if num_speakers is not None else ""

        inputs = [
            self._get_string_tensor([[audio_base64]], "AUDIO_DATA"),
            self._get_string_tensor([[num_speakers_str]], "NUM_SPEAKERS"),
        ]
        outputs = [http_client.InferRequestedOutput("DIARIZATION_RESULT")]
        return inputs, outputs

    def run_speaker_diarization_inference(
        self, audio_base64: str, num_speakers: Optional[int] = None
    ) -> Dict:
        """
        Run speaker diarization on a single base64-encoded audio.

        Returns a parsed JSON object from the diarization model.
        If the result cannot be parsed, an empty dict is returned.
        """
        if not audio_base64:
            return {}

        inputs, outputs = self.get_speaker_diarization_io_for_triton(
            audio_base64, num_speakers
        )

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.infer(
                model_name="speaker_diarization",
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except Exception as exc:  # pragma: no cover - external failure path
            logger.error(
                "Triton Speaker Diarization inference failed: %s", exc, exc_info=True
            )
            raise TritonInferenceError(
                f"Triton Speaker Diarization inference failed: {exc}"
            ) from exc

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

        if isinstance(result_bytes, bytes):
            result_str = result_bytes.decode("utf-8")
        else:
            result_str = str(result_bytes)

        logger.debug(
            "Speaker Diarization Triton response preview=%s",
            result_str[:200],
        )

        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            logger.exception("Failed to parse Speaker Diarization JSON from Triton")
            return {}
