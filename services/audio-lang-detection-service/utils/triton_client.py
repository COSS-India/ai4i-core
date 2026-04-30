"""
Triton Inference Server client wrapper for Audio Language Detection.

This client sends base64-encoded audio to a Triton deployment of the
audio language detection model and parses its output.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import tritonclient.http as http_client
from tritonclient.utils import np_to_triton_dtype

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""

    pass


class TritonClient:
    """Triton Inference Server client for Audio Language Detection operations."""

    def __init__(self, triton_url: str, api_key: Optional[str] = None, timeout: float = 300.0, model_name: Optional[str] = None):
        """
        :param triton_url: Triton server URL (host:port or http://host:port).
        :param api_key: Optional Bearer token for Authorization header.
        :param timeout: Request timeout in seconds (default: 300.0).
        :param model_name: Triton model name (REQUIRED - resolved via Model Management).
        """
        if not model_name:
            raise ValueError("model_name is required and must be resolved via Model Management")
        self.triton_url = self._normalize_url(triton_url)
        self.api_key = api_key
        self.timeout = timeout
        self.model_name = model_name
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
                "Initializing Triton client for Audio Language Detection with URL: %s",
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

    def get_audio_lang_detection_io_for_triton(
        self, audio_base64: str
    ) -> Tuple[List[http_client.InferInput], List[http_client.InferRequestedOutput]]:
        """
        Prepare inputs and outputs for audio language detection inference.

        Args:
            audio_base64: Base64-encoded audio string

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        # Shape needs to be [1, 1] for Triton (batch_size=1, num_elements=1)
        inputs = [
            self._get_string_tensor([[audio_base64]], "AUDIO_DATA"),
        ]
        outputs = [
            http_client.InferRequestedOutput("LANGUAGE_CODE"),
            http_client.InferRequestedOutput("CONFIDENCE"),
            http_client.InferRequestedOutput("ALL_SCORES"),
        ]
        return inputs, outputs

    def run_audio_lang_detection_inference(
        self, audio_base64: str
    ) -> Dict:
        """
        Run audio language detection on a single base64-encoded audio.

        Returns a dictionary with language_code, confidence, and all_scores.
        If the result cannot be parsed, returns empty/default values.
        """
        if not audio_base64:
            return {
                "language_code": "",
                "confidence": 0.0,
                "all_scores": {
                    "predicted_language": "",
                    "confidence": 0.0,
                    "top_scores": []
                }
            }

        inputs, outputs = self.get_audio_lang_detection_io_for_triton(audio_base64)

        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
                headers=headers or None,
            )
        except Exception as exc:  # pragma: no cover - external failure path
            logger.error(
                "Triton Audio Language Detection inference failed: %s", exc, exc_info=True
            )
            raise TritonInferenceError(
                f"Triton Audio Language Detection inference failed: {exc}"
            ) from exc

        # Parse response - Get LANGUAGE_CODE, CONFIDENCE, and ALL_SCORES
        language_code_result = response.as_numpy("LANGUAGE_CODE")
        confidence_result = response.as_numpy("CONFIDENCE")
        all_scores_result = response.as_numpy("ALL_SCORES")

        if language_code_result is None or confidence_result is None or all_scores_result is None:
            logger.warning("Missing results from Triton for audio language detection")
            return {
                "language_code": "",
                "confidence": 0.0,
                "all_scores": {
                    "predicted_language": "",
                    "confidence": 0.0,
                    "top_scores": []
                }
            }

        # Decode LANGUAGE_CODE - Result shape is [1, 1], so access [0][0]
        try:
            language_code_bytes = language_code_result[0][0]
            if isinstance(language_code_bytes, bytes):
                language_code = language_code_bytes.decode("utf-8")
            else:
                language_code = str(language_code_bytes)
        except Exception:
            logger.warning("Failed to extract LANGUAGE_CODE from Triton response")
            language_code = ""

        # Get CONFIDENCE - Result shape is [1, 1], so access [0][0]
        try:
            confidence = float(confidence_result[0][0])
        except Exception:
            logger.warning("Failed to extract CONFIDENCE from Triton response")
            confidence = 0.0

        # Decode ALL_SCORES - Result shape is [1, 1], so access [0][0]
        try:
            all_scores_bytes = all_scores_result[0][0]
            if isinstance(all_scores_bytes, bytes):
                all_scores_str = all_scores_bytes.decode("utf-8")
            else:
                all_scores_str = str(all_scores_bytes)

            logger.debug(
                "Audio Language Detection ALL_SCORES preview=%s",
                all_scores_str[:200],
            )

            # Parse ALL_SCORES JSON
            try:
                all_scores_data = json.loads(all_scores_str)
                return {
                    "language_code": language_code,
                    "confidence": confidence,
                    "all_scores": {
                        "predicted_language": all_scores_data.get("predicted_language", language_code),
                        "confidence": all_scores_data.get("confidence", confidence),
                        "top_scores": all_scores_data.get("top_scores", [])
                    }
                }
            except json.JSONDecodeError:
                logger.exception("Failed to parse ALL_SCORES JSON from Triton")
                # Fallback: use the values we already extracted
                return {
                    "language_code": language_code,
                    "confidence": confidence,
                    "all_scores": {
                        "predicted_language": language_code,
                        "confidence": confidence,
                        "top_scores": []
                    }
                }
        except Exception:
            logger.warning("Failed to extract ALL_SCORES from Triton response")
            # Fallback: use the values we already extracted
            return {
                "language_code": language_code,
                "confidence": confidence,
                "all_scores": {
                    "predicted_language": language_code,
                    "confidence": confidence,
                    "top_scores": []
                }
            }

