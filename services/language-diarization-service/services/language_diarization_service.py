"""
Core business logic for Language Diarization inference.

This mirrors the behavior of Dhruva's /services/inference/language-diarization
while fitting into the microservice structure used by ASR/TTS/NMT/OCR in this repository.
"""

import base64
import logging
import time
from typing import List, Optional
from uuid import UUID
from contextlib import nullcontext

import requests

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    tracer = trace.get_tracer("language-diarization-service")
    TRACING_AVAILABLE = True
except ImportError:
    tracer = None
    TRACING_AVAILABLE = False

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
from repositories.language_diarization_repository import LanguageDiarizationRepository
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
    - Persist requests and results to database
    """

    def __init__(self, triton_client: TritonClient, repository: Optional[LanguageDiarizationRepository] = None):
        self.triton_client = triton_client
        self.repository = repository

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

    async def run_inference(
        self, 
        request: LanguageDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> LanguageDiarizationInferenceResponse:
        """
        Asynchronous language diarization inference entrypoint.
        
        Persists request and results to database if repository is available.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False
        
        # Create request record if repository is available
        if self.repository:
            try:
                model_id = request.config.serviceId if request.config else "lang_diarization"
                audio_duration = None  # Could be calculated from audio data if needed
                target_language = ""  # Default to empty for all languages
                
                request_record = await self.repository.create_request(
                    model_id=model_id,
                    audio_duration=audio_duration,
                    target_language=target_language,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id
                )
                request_id = request_record.id
                logger.info(f"Created language diarization request {request_id}")
            except Exception as e:
                logger.error(f"Failed to create request record: {e}")
                # Continue without persistence
        
        output_list: List[LanguageDiarizationOutput] = []

        # Process each audio input with tracing
        if tracer:
            audio_loop_span_context = tracer.start_as_current_span("language_diarization.process_audio_loop")
        else:
            audio_loop_span_context = nullcontext()
        
        with audio_loop_span_context as audio_loop_span:
            if audio_loop_span:
                audio_loop_span.set_attribute("language_diarization.audio_count", len(request.audio))
            
            for idx, audio_item in enumerate(request.audio):
                # Resolve audio to base64 with tracing
                if tracer:
                    resolve_span_context = tracer.start_as_current_span("language_diarization.resolve_audio")
                else:
                    resolve_span_context = nullcontext()
                
                with resolve_span_context as resolve_span:
                    audio_base64 = self._resolve_audio_base64(audio_item)
                    
                    if resolve_span:
                        resolve_span.set_attribute("language_diarization.audio_index", idx + 1)
                        resolve_span.set_attribute("language_diarization.has_content", bool(audio_item.audioContent))
                        resolve_span.set_attribute("language_diarization.has_uri", bool(audio_item.audioUri))
                        if audio_base64:
                            resolve_span.set_attribute("language_diarization.audio_size_bytes", len(audio_base64))

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

                # Call Triton inference (this will create its own triton.inference span)
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

                    # Map the response to output format with tracing
                    if tracer:
                        extract_span_context = tracer.start_as_current_span("language_diarization.extract_results")
                    else:
                        extract_span_context = nullcontext()
                    
                    with extract_span_context as extract_span:
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

                        if extract_span:
                            extract_span.set_attribute("language_diarization.segment_count", len(segments_list))
                            extract_span.set_attribute("language_diarization.target_language", target_language)

                        output = LanguageDiarizationOutput(
                            total_segments=len(segments_list),
                            segments=segments_list,
                            target_language=target_language,
                        )
                        output_list.append(output)
                    
                    # Persist result if repository is available
                    if self.repository and request_id:
                        try:
                            # Convert segments to dict format for JSONB storage
                            segments_dict = [
                                {
                                    "start_time": seg.start_time,
                                    "end_time": seg.end_time,
                                    "duration": seg.duration,
                                    "language": seg.language,
                                    "confidence": seg.confidence
                                }
                                for seg in segments_list
                            ]
                            await self.repository.create_result(
                                request_id=request_id,
                                total_segments=len(segments_list),
                                segments=segments_dict,
                                target_language=target_language
                            )
                        except Exception as e:
                            logger.error(f"Failed to create result record: {e}")

                except TritonInferenceError as exc:
                    logger.error("Language Diarization Triton inference failed: %s", exc)
                    has_errors = True
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
                    has_errors = True
                    output_list.append(
                        LanguageDiarizationOutput(
                            total_segments=0,
                            segments=[],
                            target_language=target_language,
                        )
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

