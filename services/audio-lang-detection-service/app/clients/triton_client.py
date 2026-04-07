"""Audio Language Detection-specific Triton client extending shared base."""

import json
import logging
from typing import Dict, List, Optional, Tuple

from tritonclient.http import InferInput, InferRequestedOutput

from ai4icore_model_management import TritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)


class AudioLangDetectionTritonClient(TritonClient):
    """Triton client with Audio Language Detection-specific I/O preparation."""

    def get_audio_lang_detection_io_for_triton(
        self, audio_base64: str
    ) -> Tuple[List[InferInput], List[InferRequestedOutput]]:
        """
        Prepare inputs and outputs for audio language detection inference.

        Args:
            audio_base64: Base64-encoded audio string

        Returns:
            tuple: (inputs, outputs) for Triton inference
        """
        input_tensor = self._get_string_tensor([audio_base64], "AUDIO_DATA")
        outputs = [
            InferRequestedOutput("LANGUAGE_CODE"),
            InferRequestedOutput("CONFIDENCE"),
            InferRequestedOutput("ALL_SCORES"),
        ]
        return [input_tensor], outputs

    def run_audio_lang_detection_inference(self, audio_base64: str, model_name: str) -> Dict:
        """
        Run audio language detection on a single base64-encoded audio.

        Returns a dictionary with language_code, confidence, and all_scores.
        If the result cannot be parsed, returns empty/default values.
        """
        empty_result = {
            "language_code": "",
            "confidence": 0.0,
            "all_scores": {
                "predicted_language": "",
                "confidence": 0.0,
                "top_scores": [],
            },
        }

        if not audio_base64:
            return empty_result

        inputs, outputs = self.get_audio_lang_detection_io_for_triton(audio_base64)
        response = self.send_triton_request(model_name=model_name, inputs=inputs, outputs=outputs)

        # Parse response
        language_code_result = response.as_numpy("LANGUAGE_CODE")
        confidence_result = response.as_numpy("CONFIDENCE")
        all_scores_result = response.as_numpy("ALL_SCORES")

        if language_code_result is None or confidence_result is None or all_scores_result is None:
            logger.warning("Missing results from Triton for audio language detection")
            return empty_result

        # Decode LANGUAGE_CODE - Result shape is [1, 1], so access [0][0]
        try:
            language_code_bytes = language_code_result[0][0]
            language_code = (
                language_code_bytes.decode("utf-8")
                if isinstance(language_code_bytes, bytes)
                else str(language_code_bytes)
            )
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
            all_scores_str = (
                all_scores_bytes.decode("utf-8")
                if isinstance(all_scores_bytes, bytes)
                else str(all_scores_bytes)
            )

            logger.debug("Audio Language Detection ALL_SCORES preview=%s", all_scores_str[:200])

            try:
                all_scores_data = json.loads(all_scores_str)
                return {
                    "language_code": language_code,
                    "confidence": confidence,
                    "all_scores": {
                        "predicted_language": all_scores_data.get("predicted_language", language_code),
                        "confidence": all_scores_data.get("confidence", confidence),
                        "top_scores": all_scores_data.get("top_scores", []),
                    },
                }
            except json.JSONDecodeError:
                logger.exception("Failed to parse ALL_SCORES JSON from Triton")
                return {
                    "language_code": language_code,
                    "confidence": confidence,
                    "all_scores": {
                        "predicted_language": language_code,
                        "confidence": confidence,
                        "top_scores": [],
                    },
                }
        except Exception:
            logger.warning("Failed to extract ALL_SCORES from Triton response")
            return {
                "language_code": language_code,
                "confidence": confidence,
                "all_scores": {
                    "predicted_language": language_code,
                    "confidence": confidence,
                    "top_scores": [],
                },
            }
