"""
Core business logic for Language Diarization inference.

This mirrors the behavior of Dhruva's /services/inference/language-diarization
while fitting into the microservice structure used by ASR/TTS/NMT/OCR in this repository.
"""

import base64
import logging
from typing import List, Optional

import requests

from models.language_diarization_request import (
    AudioInput,
    LanguageDiarizationInferenceRequest,
)
from models.language_diarization_response import (
    LanguageSegment,
    LanguageDiarizationInferenceResponse,
    LanguageDiarizationOutput,
    LanguageDiarizationResponseConfig,
)
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)


class LanguageDiarizationService:
    """
    Language Diarization inference service.

    Responsibilities:
    - Take LanguageDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Language Diarization model)
      - Map diarization model output to LanguageDiarizationInferenceResponse
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
        self, request: LanguageDiarizationInferenceRequest
    ) -> LanguageDiarizationInferenceResponse:
        """
        Synchronous language diarization inference entrypoint.

        NOTE: This is intentionally synchronous like ASR/TTS/OCR core services; the
        FastAPI router can call it from an async endpoint.
        """
        output_list: List[LanguageDiarizationOutput] = []

        # Process each audio input
        for audio_item in request.audio:
            # Resolve audio to base64
            audio_base64 = self._resolve_audio_base64(audio_item)

            if not audio_base64:
                # Skip if no audio data
                output_list.append(
                    LanguageDiarizationOutput(
                        total_segments=0,
                        segments=[],
                        target_language="",
                    )
                )
                continue

            # target_language defaults to empty string for detecting all languages
            target_language = ""

            # Call Triton inference
            try:
                diarization_data = self.triton_client.run_language_diarization_inference(
                    audio_base64, target_language
                )

                if not diarization_data:
                    # Empty response from Triton
                    output_list.append(
                        LanguageDiarizationOutput(
                            total_segments=0,
                            segments=[],
                            target_language=target_language,
                        )
                    )
                    continue

                # Map the response to output format
                segments_list: List[LanguageSegment] = []

                # Extract segments
                raw_segments = diarization_data.get("segments", [])
                for seg in raw_segments:
                    language = seg.get("language", "")
                    start_time = float(seg.get("start_time", 0.0))
                    end_time = float(seg.get("end_time", 0.0))
                    duration = float(seg.get("duration", end_time - start_time))
                    confidence = float(seg.get("confidence", 0.0))

                    segments_list.append(
                        LanguageSegment(
                            start_time=start_time,
                            end_time=end_time,
                            duration=duration,
                            language=language,
                            confidence=confidence,
                        )
                    )

                # Sort segments by start_time
                segments_list.sort(key=lambda x: x.start_time)

                # Get target_language from response or use default
                target_language = diarization_data.get("target_language", target_language)

                output_list.append(
                    LanguageDiarizationOutput(
                        total_segments=len(segments_list),
                        segments=segments_list,
                        target_language=target_language,
                    )
                )

            except TritonInferenceError as exc:
                logger.error("Language Diarization Triton inference failed: %s", exc)
                output_list.append(
                    LanguageDiarizationOutput(
                        total_segments=0,
                        segments=[],
                        target_language=target_language,
                    )
                )
            except Exception as exc:
                logger.error(
                    "Error in language diarization inference: %s", exc, exc_info=True
                )
                output_list.append(
                    LanguageDiarizationOutput(
                        total_segments=0,
                        segments=[],
                        target_language=target_language,
                    )
                )

        # Create response config
        response_config = None
        if request.config.serviceId:
            response_config = LanguageDiarizationResponseConfig(
                serviceId=request.config.serviceId,
            )

        return LanguageDiarizationInferenceResponse(
            taskType="language-diarization",
            output=output_list,
            config=response_config,
        )

