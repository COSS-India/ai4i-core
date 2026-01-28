"""
Core business logic for Speaker Diarization inference.

This mirrors the behavior of Dhruva's /services/inference/speaker-diarization
while fitting into the microservice structure used by ASR/TTS/NMT/OCR in this repository.
"""

import base64
import logging
import time
from typing import List, Optional
from uuid import UUID

import requests
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

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
from repositories.speaker_diarization_repository import SpeakerDiarizationRepository
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
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

    def __init__(self, triton_client: TritonClient, repository: Optional[SpeakerDiarizationRepository] = None):
        self.triton_client = triton_client
        self.repository = repository

    def _resolve_audio_base64(self, audio: AudioInput, audio_idx: int = 0) -> Optional[str]:
        """
        Resolve an audio into base64 with detailed tracing:

        - If audioContent is provided, use it directly
        - Else, download from audioUri and base64-encode it
        """
        try:
            with tracer.start_as_current_span("speaker_diarization.resolve_audio") as span:
                span.set_attribute("audio.index", audio_idx)
                
                if audio.audioContent:
                    span.set_attribute("audio.source", "direct_content")
                    span.set_attribute("audio.size_bytes", len(audio.audioContent))
                    span.add_event("audio.resolved_from_content")
                    return audio.audioContent

                if audio.audioUri:
                    span.set_attribute("audio.source", "uri")
                    span.set_attribute("audio.uri", str(audio.audioUri))
                    span.add_event("audio.download_start", {"uri": str(audio.audioUri)})
                    
                    try:
                        resp = requests.get(str(audio.audioUri), timeout=300)
                        resp.raise_for_status()
                        
                        audio_content = resp.content
                        span.set_attribute("audio.downloaded_bytes", len(audio_content))
                        span.add_event("audio.download_complete", {"size_bytes": len(audio_content)})
                        
                        encoded = base64.b64encode(audio_content).decode("utf-8")
                        span.set_attribute("audio.encoded_size_bytes", len(encoded))
                        span.add_event("audio.base64_encoded")
                        return encoded
                        
                    except Exception as exc:
                        span.set_attribute("error", True)
                        span.set_attribute("error.type", type(exc).__name__)
                        span.set_attribute("error.message", str(exc))
                        span.set_status(Status(StatusCode.ERROR))
                        span.record_exception(exc)
                        logger.error(
                            "Failed to download audio from %s: %s", audio.audioUri, exc
                        )
                        return None

                # No content and no URI
                span.set_attribute("audio.source", "none")
                span.add_event("audio.no_source_provided")
                return None
                
        except AttributeError:
            # Tracer not available, use simple implementation
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

            return None

    async def run_inference(
        self, 
        request: SpeakerDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> SpeakerDiarizationInferenceResponse:
        """
        Asynchronous speaker diarization inference entrypoint.
        
        Persists request and results to database if repository is available.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False
        
        # Create request record if repository is available
        if self.repository:
            try:
                model_id = request.config.serviceId if request.config and request.config.serviceId else None
                if not model_id:
                    logger.warning("No serviceId provided in request config for database logging")
                # Calculate total audio duration (estimate from base64 size if needed)
                audio_duration = None  # Could be calculated from audio data if needed
                num_speakers = None  # Will be determined by model
                
                request_record = await self.repository.create_request(
                    model_id=model_id,
                    audio_duration=audio_duration,
                    num_speakers=num_speakers,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id
                )
                request_id = request_record.id
                logger.info(f"Created speaker diarization request {request_id}")
            except Exception as e:
                logger.error(f"Failed to create request record: {e}")
                # Continue without persistence
        
        output_list: List[SpeakerDiarizationOutput] = []

        # Process each audio input
        for audio_idx, audio_item in enumerate(request.audio):
            # Resolve audio to base64
            audio_base64 = self._resolve_audio_base64(audio_item, audio_idx)

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

                # Map the response to output format with detailed tracing
                try:
                    with tracer.start_as_current_span("speaker_diarization.process_results") as result_span:
                        result_span.set_attribute("audio.index", audio_idx)
                        result_span.add_event("processing.start")
                        
                        segments_list: List[Segment] = []
                        speakers_set = set()

                        # Extract segments
                        raw_segments = diarization_data.get("segments", [])
                        result_span.set_attribute("raw.num_segments", len(raw_segments))
                        
                        for seg_idx, seg in enumerate(raw_segments):
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

                        result_span.set_attribute("processed.num_segments", len(segments_list))
                        result_span.set_attribute("processed.num_speakers", len(speakers_set))
                        result_span.set_attribute("processed.speakers", ",".join(sorted(speakers_set)))
                        result_span.add_event("processing.complete", {
                            "segments": len(segments_list),
                            "speakers": len(speakers_set)
                        })

                        output = SpeakerDiarizationOutput(
                            total_segments=len(segments_list),
                            num_speakers=len(speakers_set),
                            speakers=sorted(list(speakers_set)),
                            segments=segments_list,
                        )
                        output_list.append(output)
                        
                except AttributeError:
                    # Tracer not available, use simple implementation
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

                    output = SpeakerDiarizationOutput(
                        total_segments=len(segments_list),
                        num_speakers=len(speakers_set),
                        speakers=sorted(list(speakers_set)),
                        segments=segments_list,
                    )
                    output_list.append(output)
                
                # Persist result if repository is available
                if self.repository and request_id:
                    try:
                        with tracer.start_as_current_span("speaker_diarization.store_result") as store_span:
                            store_span.set_attribute("audio.index", audio_idx)
                            store_span.set_attribute("request_id", str(request_id))
                            store_span.set_attribute("num_segments", len(segments_list))
                            store_span.set_attribute("num_speakers", len(speakers_set))
                            
                            # Convert segments to dict format for JSONB storage
                            segments_dict = [
                                {
                                    "start_time": seg.start_time,
                                    "end_time": seg.end_time,
                                    "duration": seg.duration,
                                    "speaker": seg.speaker
                                }
                                for seg in segments_list
                            ]
                            await self.repository.create_result(
                                request_id=request_id,
                                total_segments=len(segments_list),
                                num_speakers=len(speakers_set),
                                speakers=sorted(list(speakers_set)),
                                segments=segments_dict
                            )
                            store_span.add_event("result.stored", {"status": "success"})
                    except AttributeError:
                        # Tracer not available, use simple implementation
                        segments_dict = [
                            {
                                "start_time": seg.start_time,
                                "end_time": seg.end_time,
                                "duration": seg.duration,
                                "speaker": seg.speaker
                            }
                            for seg in segments_list
                        ]
                        await self.repository.create_result(
                            request_id=request_id,
                            total_segments=len(segments_list),
                            num_speakers=len(speakers_set),
                            speakers=sorted(list(speakers_set)),
                            segments=segments_dict
                        )
                    except Exception as e:
                        logger.error(f"Failed to create result record: {e}")

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
                has_errors = True
            except Exception as exc:
                logger.error(
                    "Error in speaker diarization inference: %s", exc, exc_info=True
                )
                has_errors = True
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

        # Update request status if repository is available
        if self.repository and request_id:
            try:
                processing_time = time.time() - start_time
                status = "failed" if has_errors else "completed"
                await self.repository.update_request_status(
                    request_id=request_id,
                    status=status,
                    processing_time=processing_time
                )
            except Exception as e:
                logger.error(f"Failed to update request status: {e}")

        return SpeakerDiarizationInferenceResponse(
            taskType="speaker-diarization",
            output=output_list,
            config=response_config,
        )

