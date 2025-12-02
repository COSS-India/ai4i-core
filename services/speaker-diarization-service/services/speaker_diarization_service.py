"""
Core business logic for Speaker Diarization inference.

This mirrors the behavior of Dhruva's /services/inference/speaker-diarization
while fitting into the microservice structure used by ASR/TTS/NMT/OCR in this repository.
"""

import base64
import logging
from typing import List, Optional

import requests

from models.speaker_diarization_request import (
    AudioInput,
    SpeakerDiarizationInferenceRequest,
)
from models.speaker_diarization_response import (
    Segment,
    SpeakerDiarizationInferenceResponse,
    SpeakerDiarizationOutput,
    SpeakerDiarizationResponseConfig,
)
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)


class SpeakerDiarizationService:
    """
    Speaker Diarization inference service.

    Responsibilities:
    - Take SpeakerDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Speaker Diarization model)
      - Map diarization model output to SpeakerDiarizationInferenceResponse
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
        self, request: SpeakerDiarizationInferenceRequest
    ) -> SpeakerDiarizationInferenceResponse:
        """
        Synchronous speaker diarization inference entrypoint.

        NOTE: This is intentionally synchronous like ASR/TTS/OCR core services; the
        FastAPI router can call it from an async endpoint.
        """
        output_list: List[SpeakerDiarizationOutput] = []

        # Process each audio input
        for audio_item in request.audio:
            # Resolve audio to base64
            audio_base64 = self._resolve_audio_base64(audio_item)

            if not audio_base64:
                # Skip if no audio data
                output_list.append(
                    SpeakerDiarizationOutput(
                        total_segments=0,
                        num_speakers=0,
                        speakers=[],
                        segments=[],
                    )
                )
                continue

            # num_speakers will be auto-detected by the model if not provided (None)
            num_speakers = None

            # Call Triton inference
            try:
                diarization_data = self.triton_client.run_speaker_diarization_inference(
                    audio_base64, num_speakers
                )

                if not diarization_data:
                    # Empty response from Triton
                    output_list.append(
                        SpeakerDiarizationOutput(
                            total_segments=0,
                            num_speakers=0,
                            speakers=[],
                            segments=[],
                        )
                    )
                    continue

                # Map the response to output format
                segments_list: List[Segment] = []
                speakers_set = set()

                # Extract segments
                raw_segments = diarization_data.get("segments", [])
                for seg in raw_segments:
                    speaker = seg.get("speaker", "")
                    start_time = float(seg.get("start_time", 0.0))
                    end_time = float(seg.get("end_time", 0.0))
                    duration = end_time - start_time

                    if speaker:
                        speakers_set.add(speaker)

                    segments_list.append(
                        Segment(
                            start_time=start_time,
                            end_time=end_time,
                            duration=duration,
                            speaker=speaker,
                        )
                    )

                # Sort segments by start_time
                segments_list.sort(key=lambda x: x.start_time)

                output_list.append(
                    SpeakerDiarizationOutput(
                        total_segments=len(segments_list),
                        num_speakers=len(speakers_set),
                        speakers=sorted(list(speakers_set)),
                        segments=segments_list,
                    )
                )

            except TritonInferenceError as exc:
                logger.error("Speaker Diarization Triton inference failed: %s", exc)
                output_list.append(
                    SpeakerDiarizationOutput(
                        total_segments=0,
                        num_speakers=0,
                        speakers=[],
                        segments=[],
                    )
                )
            except Exception as exc:
                logger.error(
                    "Error in speaker diarization inference: %s", exc, exc_info=True
                )
                output_list.append(
                    SpeakerDiarizationOutput(
                        total_segments=0,
                        num_speakers=0,
                        speakers=[],
                        segments=[],
                    )
                )

        # Create response config
        response_config = None
        if request.config.serviceId:
            response_config = SpeakerDiarizationResponseConfig(
                serviceId=request.config.serviceId,
                language=None,
            )

        return SpeakerDiarizationInferenceResponse(
            taskType="speaker-diarization",
            output=output_list,
            config=response_config,
        )

