"""
Core business logic for Language Diarization inference.
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
    LanguageDiarizationInferenceRequest,
    LanguageSegment,
    LanguageDiarizationInferenceResponse,
    LanguageDiarizationOutput,
    LanguageDiarizationResponseConfig,
)
from app.repositories.language_diarization_repository import LanguageDiarizationRepository
from app.clients.triton_client import LanguageDiarizationTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("language-diarization-service")


class LanguageDiarizationService:
    """
    Language Diarization inference service.

    Responsibilities:
    - Take LanguageDiarizationInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Language Diarization model)
      - Map diarization model output to response format
    - Persist requests and results to database
    """

    def __init__(
        self,
        triton_client: LanguageDiarizationTritonClient,
        repository: Optional[LanguageDiarizationRepository] = None,
    ):
        self.triton_client = triton_client
        self.repository = repository

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """Resolve an audio into base64.

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

        return None

    async def run_inference(
        self,
        request: LanguageDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> LanguageDiarizationInferenceResponse:
        """Asynchronous language diarization inference entrypoint."""
        try:
            return await self._do_inference(request, user_id, api_key_id, session_id)
        except TritonInferenceError:
            raise

    async def _do_inference(
        self,
        request: LanguageDiarizationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> LanguageDiarizationInferenceResponse:
        """Internal inference implementation."""
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False

        # Create request record if repository is available
        if self.repository:
            try:
                model_id = request.config.serviceId if request.config else "lang_diarization"
                request_record = await self.repository.create_request(
                    model_id=model_id,
                    audio_duration=None,
                    target_language="",
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                )
                request_id = request_record.id
                logger.info(f"Created language diarization request {request_id}")
            except Exception as e:
                logger.error(f"Failed to create request record: {e}")

        output_list: List[LanguageDiarizationOutput] = []

        with tracer.start_as_current_span("language_diarization.process_audio_loop") as audio_loop_span:
            audio_loop_span.set_attribute("language_diarization.audio_count", len(request.audio))

            for idx, audio_item in enumerate(request.audio):
                # Resolve audio to base64
                with tracer.start_as_current_span("language_diarization.resolve_audio") as resolve_span:
                    audio_base64 = self._resolve_audio_base64(audio_item)
                    resolve_span.set_attribute("language_diarization.audio_index", idx + 1)
                    resolve_span.set_attribute("language_diarization.has_content", bool(audio_item.audioContent))
                    resolve_span.set_attribute("language_diarization.has_uri", bool(audio_item.audioUri))
                    if audio_base64:
                        resolve_span.set_attribute("language_diarization.audio_size_bytes", len(audio_base64))

                if not audio_base64:
                    output_list.append(
                        LanguageDiarizationOutput(
                            total_segments=0,
                            segments=[],
                            target_language="",
                        )
                    )
                    continue

                target_language = ""

                try:
                    diarization_data = self.triton_client.run_language_diarization_inference(
                        audio_base64, target_language
                    )

                    if not diarization_data:
                        output_list.append(
                            LanguageDiarizationOutput(
                                total_segments=0,
                                segments=[],
                                target_language=target_language,
                            )
                        )
                        continue

                    # Map response to output format
                    with tracer.start_as_current_span("language_diarization.extract_results") as extract_span:
                        segments_list: List[LanguageSegment] = []

                        raw_segments = diarization_data.get("segments", [])
                        for seg in raw_segments:
                            language = seg.get("language", "")
                            seg_start = float(seg.get("start_time", 0.0))
                            seg_end = float(seg.get("end_time", 0.0))
                            duration = float(seg.get("duration", seg_end - seg_start))
                            confidence = float(seg.get("confidence", 0.0))

                            segments_list.append(
                                LanguageSegment(
                                    start_time=seg_start,
                                    end_time=seg_end,
                                    duration=duration,
                                    language=language,
                                    confidence=confidence,
                                )
                            )

                        segments_list.sort(key=lambda x: x.start_time)
                        target_language = diarization_data.get("target_language", target_language)

                        extract_span.set_attribute("language_diarization.segment_count", len(segments_list))
                        extract_span.set_attribute("language_diarization.target_language", target_language)

                        output = LanguageDiarizationOutput(
                            total_segments=len(segments_list),
                            segments=segments_list,
                            target_language=target_language,
                        )
                        output_list.append(output)

                    # Persist result
                    if self.repository and request_id:
                        try:
                            segments_dict = [
                                {
                                    "start_time": seg.start_time,
                                    "end_time": seg.end_time,
                                    "duration": seg.duration,
                                    "language": seg.language,
                                    "confidence": seg.confidence,
                                }
                                for seg in segments_list
                            ]
                            await self.repository.create_result(
                                request_id=request_id,
                                total_segments=len(segments_list),
                                segments=segments_dict,
                                target_language=target_language,
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

        # Update request status
        if self.repository and request_id:
            try:
                processing_time = time.time() - start_time
                req_status = "failed" if has_errors else "completed"
                await self.repository.update_request_status(
                    request_id=request_id,
                    status=req_status,
                    processing_time=processing_time,
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
