"""
Core business logic for Audio Language Detection inference.

This mirrors the behavior of Dhruva's /services/inference/audio-lang-detection
while fitting into the microservice structure used by ASR/TTS/NMT/OCR in this repository.
"""

import base64
import logging
from typing import List, Optional

import requests

from models.audio_lang_detection_request import (
    AudioInput,
    AudioLangDetectionInferenceRequest,
)
from models.audio_lang_detection_response import (
    AllScores,
    AudioLangDetectionInferenceResponse,
    AudioLangDetectionOutput,
    AudioLangDetectionResponseConfig,
)
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)


class AudioLangDetectionService:
    """
    Audio Language Detection inference service.

    Responsibilities:
    - Take AudioLangDetectionInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Audio Language Detection model)
      - Map detection model output to AudioLangDetectionInferenceResponse
    """

    def __init__(self, triton_client: TritonClient):
        self.triton_client = triton_client

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """
        Resolve an audio into base64:

        - If audioContent is provided, use it directly
        - Else, download from audioUri and base64-encode it
        """
        if audio.audioContent:
            return audio.audioContent

        if audio.audioUri:
            try:
                resp = requests.get(str(audio.audioUri), timeout=300)
                resp.raise_for_status()
                return base64.b64encode(resp.content).decode("utf-8")
            except Exception as exc:
                logger.error(
                    "Failed to download audio from %s: %s", audio.audioUri, exc
                )
                return None

        # No content and no URI
        return None

    def run_inference(
        self, request: AudioLangDetectionInferenceRequest
    ) -> AudioLangDetectionInferenceResponse:
        """
        Synchronous audio language detection inference entrypoint.

        NOTE: This is intentionally synchronous like ASR/TTS/OCR core services; the
        FastAPI router can call it from an async endpoint.
        """
        output_list: List[AudioLangDetectionOutput] = []

        # Process each audio input
        for audio_item in request.audio:
            # Resolve audio to base64
            audio_base64 = self._resolve_audio_base64(audio_item)

            if not audio_base64:
                # Skip if no audio data
                output_list.append(
                    AudioLangDetectionOutput(
                        language_code="",
                        confidence=0.0,
                        all_scores=AllScores(
                            predicted_language="",
                            confidence=0.0,
                            top_scores=[],
                        ),
                    )
                )
                continue

            # Call Triton inference
            try:
                detection_data = self.triton_client.run_audio_lang_detection_inference(
                    audio_base64
                )

                if not detection_data:
                    # Empty response from Triton
                    output_list.append(
                        AudioLangDetectionOutput(
                            language_code="",
                            confidence=0.0,
                            all_scores=AllScores(
                                predicted_language="",
                                confidence=0.0,
                                top_scores=[],
                            ),
                        )
                    )
                    continue

                # Map the response to output format
                all_scores_data = detection_data.get("all_scores", {})
                output_list.append(
                    AudioLangDetectionOutput(
                        language_code=detection_data.get("language_code", ""),
                        confidence=detection_data.get("confidence", 0.0),
                        all_scores=AllScores(
                            predicted_language=all_scores_data.get("predicted_language", ""),
                            confidence=all_scores_data.get("confidence", 0.0),
                            top_scores=all_scores_data.get("top_scores", []),
                        ),
                    )
                )

            except TritonInferenceError as exc:
                logger.error("Audio Language Detection Triton inference failed: %s", exc)
                output_list.append(
                    AudioLangDetectionOutput(
                        language_code="",
                        confidence=0.0,
                        all_scores=AllScores(
                            predicted_language="",
                            confidence=0.0,
                            top_scores=[],
                        ),
                    )
                )
            except Exception as exc:
                logger.error(
                    "Error in audio language detection inference: %s", exc, exc_info=True
                )
                output_list.append(
                    AudioLangDetectionOutput(
                        language_code="",
                        confidence=0.0,
                        all_scores=AllScores(
                            predicted_language="",
                            confidence=0.0,
                            top_scores=[],
                        ),
                    )
                )

        # Create response config
        response_config = None
        if request.config.serviceId:
            response_config = AudioLangDetectionResponseConfig(
                serviceId=request.config.serviceId,
            )

        return AudioLangDetectionInferenceResponse(
            taskType="audio-lang-detection",
            output=output_list,
            config=response_config,
        )

