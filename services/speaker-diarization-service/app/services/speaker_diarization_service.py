"""
Core business logic for Speaker Diarization inference.
"""

import base64
import logging
import time
from typing import List, Optional
from uuid import UUID

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import (
    AudioInput,
    Segment,
    SpeakerDiarizationInferenceRequest,
    SpeakerDiarizationInferenceResponse,
    SpeakerDiarizationOutput,
    SpeakerDiarizationResponseConfig,
)
from app.repositories.speaker_diarization_repository import SpeakerDiarizationRepository
from app.clients.triton_client import SpeakerDiarizationTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("speaker-diarization-service")


class SpeakerDiarizationService:
    """
    Speaker Diarization inference service.

    Responsibilities:
    - Take SpeakerDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Speaker Diarization model)
      - Map diarization model output to SpeakerDiarizationInferenceResponse
    - Persist requests and results to database
    """

    def __init__(
        self,
        repository: SpeakerDiarizationRepository,
        triton_client: SpeakerDiarizationTritonClient,
        model_name: str,
    ):
        self.repository = repository
        self.triton_client = triton_client
        self.model_name = model_name

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """
        Resolve an audio into base64:

        - If audioContent is provided, use it directly
        - Else, download from audioUri and base64-encode it
        """
        with tracer.start_as_current_span("speaker-diarization.resolve_audio") as span:
            if audio.audioContent:
                span.set_attribute("audio.source", "content")
                span.set_attribute("audio.size_bytes", len(audio.audioContent))
                return audio.audioContent

            if audio.audioUri:
                span.set_attribute("audio.source", "uri")
                span.set_attribute("audio.uri", str(audio.audioUri))
                try:
                    resp = requests.get(str(audio.audioUri), timeout=300)
                    resp.raise_for_status()
                    encoded = base64.b64encode(resp.content).decode("utf-8")
                    span.set_attribute("audio.size_bytes", len(encoded))
                    return encoded
                except Exception as exc:
                    span.set_attribute("error", True)
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    logger.error("Failed to download audio from %s: %s", audio.audioUri, exc)
                    return None

            span.set_attribute("audio.source", "none")
            return None

    def _empty_output(self) -> SpeakerDiarizationOutput:
        """Return an empty output for failed/missing audio."""
        return SpeakerDiarizationOutput(
            total_segments=0,
            num_speakers=0,
            speakers=[],
            segments=[],
        )

    async def run_inference(
        self,
        request: SpeakerDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> SpeakerDiarizationInferenceResponse:
        """
        Async speaker diarization inference entrypoint.

        Creates database request record, processes inference, logs results, and updates status.
        OpenTelemetry's tracer.start_as_current_span() is a no-op when tracing isn't configured.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False

        with tracer.start_as_current_span("speaker-diarization.process_batch") as span:
            try:
                service_id = request.config.serviceId
                span.set_attribute("speaker-diarization.total_audio", len(request.audio))
                span.set_attribute("speaker-diarization.service_id", service_id)
                span.set_attribute("speaker-diarization.model_name", self.model_name)

                if user_id:
                    span.set_attribute("user.id", str(user_id))
                if api_key_id:
                    span.set_attribute("api_key.id", str(api_key_id))
                if session_id:
                    span.set_attribute("session.id", str(session_id))

                # Create request record
                try:
                    request_record = await self.repository.create_request(
                        model_id=service_id,
                        audio_duration=None,
                        num_speakers=None,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = request_record.id
                    span.set_attribute("speaker-diarization.request_id", str(request_id))
                    logger.info(f"Created speaker diarization request {request_id}")
                except Exception as e:
                    logger.error(f"Failed to create request record: {e}")

                output_list: List[SpeakerDiarizationOutput] = []

                # Process each audio input
                for audio_idx, audio_item in enumerate(request.audio):
                    audio_base64 = self._resolve_audio_base64(audio_item)

                    if not audio_base64:
                        output_list.append(self._empty_output())
                        continue

                    # num_speakers will be auto-detected by the model if not provided
                    num_speakers = None

                    with tracer.start_as_current_span("speaker-diarization.triton_inference") as inference_span:
                        inference_span.set_attribute("speaker-diarization.audio_index", audio_idx)
                        try:
                            diarization_data = self.triton_client.run_speaker_diarization_inference(
                                audio_base64, num_speakers, model_name=self.model_name
                            )

                            if not diarization_data:
                                output_list.append(self._empty_output())
                                continue

                            # Map the response to output format
                            segments_list: List[Segment] = []
                            speakers_set = set()

                            raw_segments = diarization_data.get("segments", [])
                            for seg in raw_segments:
                                speaker = seg.get("speaker", "")
                                seg_start = float(seg.get("start_time", 0.0))
                                seg_end = float(seg.get("end_time", 0.0))
                                duration = seg_end - seg_start

                                if speaker:
                                    speakers_set.add(speaker)

                                segments_list.append(
                                    Segment(
                                        start_time=seg_start,
                                        end_time=seg_end,
                                        duration=duration,
                                        speaker=speaker,
                                    )
                                )

                            # Sort segments by start_time
                            segments_list.sort(key=lambda x: x.start_time)

                            inference_span.set_attribute("speaker-diarization.num_segments", len(segments_list))
                            inference_span.set_attribute("speaker-diarization.num_speakers", len(speakers_set))

                            output = SpeakerDiarizationOutput(
                                total_segments=len(segments_list),
                                num_speakers=len(speakers_set),
                                speakers=sorted(list(speakers_set)),
                                segments=segments_list,
                            )
                            output_list.append(output)

                            # Persist result
                            if request_id:
                                try:
                                    segments_dict = [
                                        {
                                            "start_time": seg.start_time,
                                            "end_time": seg.end_time,
                                            "duration": seg.duration,
                                            "speaker": seg.speaker,
                                        }
                                        for seg in segments_list
                                    ]
                                    await self.repository.create_result(
                                        request_id=request_id,
                                        total_segments=len(segments_list),
                                        num_speakers=len(speakers_set),
                                        speakers=sorted(list(speakers_set)),
                                        segments=segments_dict,
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to create result record: {e}")

                        except TritonInferenceError as exc:
                            inference_span.set_attribute("error", True)
                            inference_span.set_attribute("error.type", "TritonInferenceError")
                            inference_span.set_attribute("error.message", str(exc))
                            inference_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            inference_span.record_exception(exc)
                            logger.error("Speaker Diarization Triton inference failed: %s", exc)
                            has_errors = True
                            output_list.append(self._empty_output())

                        except Exception as exc:
                            inference_span.set_attribute("error", True)
                            inference_span.set_attribute("error.type", type(exc).__name__)
                            inference_span.set_attribute("error.message", str(exc))
                            inference_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            inference_span.record_exception(exc)
                            logger.error("Error in speaker diarization inference: %s", exc, exc_info=True)
                            has_errors = True
                            output_list.append(self._empty_output())

                # Create response config
                response_config = None
                if request.config.serviceId:
                    response_config = SpeakerDiarizationResponseConfig(
                        serviceId=request.config.serviceId,
                        language=None,
                    )

                # Update request status
                if request_id:
                    try:
                        processing_time = time.time() - start_time
                        status_str = "failed" if has_errors else "completed"
                        span.set_attribute("speaker-diarization.processing_time_seconds", processing_time)
                        span.set_attribute("speaker-diarization.status", status_str)
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status=status_str,
                            processing_time=processing_time,
                        )
                    except Exception as e:
                        logger.error(f"Failed to update request status: {e}")

                span.set_attribute("speaker-diarization.output_count", len(output_list))
                span.set_attribute("speaker-diarization.has_errors", has_errors)

                return SpeakerDiarizationInferenceResponse(
                    taskType="speaker-diarization",
                    output=output_list,
                    config=response_config,
                )

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Speaker diarization inference failed: {e}")

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                raise
