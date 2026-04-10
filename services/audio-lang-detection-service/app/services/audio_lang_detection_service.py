"""
Core business logic for Audio Language Detection inference.
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
    AudioLangDetectionInferenceRequest,
    AudioLangDetectionInferenceResponse,
    AudioLangDetectionOutput,
    AudioLangDetectionResponseConfig,
    AllScores,
)
from app.repositories.audio_lang_detection_repository import AudioLangDetectionRepository
from app.clients.triton_client import AudioLangDetectionTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("audio-lang-detection-service")


class AudioLangDetectionService:
    """
    Audio Language Detection inference service.

    Responsibilities:
    - Take AudioLangDetectionInferenceRequest
    - For each audio:
      - Resolve base64 content (direct or via audioUri download)
      - Call Triton (Audio Language Detection model)
      - Map detection model output to AudioLangDetectionInferenceResponse
    - Persist requests and results to database
    """

    def __init__(
        self,
        repository: AudioLangDetectionRepository,
        triton_client: AudioLangDetectionTritonClient,
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
        with tracer.start_as_current_span("audio-lang-detection.resolve_audio") as span:
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
                    audio_bytes = base64.b64encode(resp.content).decode("utf-8")
                    span.set_attribute("audio.size_bytes", len(audio_bytes))
                    return audio_bytes
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

    def _empty_output(self) -> AudioLangDetectionOutput:
        """Return an empty output for failed/missing audio."""
        return AudioLangDetectionOutput(
            language_code="",
            confidence=0.0,
            all_scores=AllScores(
                predicted_language="",
                confidence=0.0,
                top_scores=[],
            ),
        )

    async def run_inference(
        self,
        request: AudioLangDetectionInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
    ) -> AudioLangDetectionInferenceResponse:
        """
        Async audio language detection inference entrypoint.

        Creates database request record, processes inference, logs results, and updates status.
        OpenTelemetry's tracer.start_as_current_span() is a no-op when tracing isn't configured.
        """
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False

        with tracer.start_as_current_span("audio-lang-detection.process_batch") as span:
            try:
                service_id = request.config.serviceId
                span.set_attribute("audio-lang-detection.total_audio", len(request.audio))
                span.set_attribute("audio-lang-detection.service_id", service_id)
                span.set_attribute("audio-lang-detection.model_name", self.model_name)

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
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                    )
                    request_id = request_record.id
                    span.set_attribute("audio-lang-detection.request_id", str(request_id))
                    logger.info(f"Created audio language detection request {request_id}")
                except Exception as e:
                    logger.error(f"Failed to create request record: {e}")

                # Resolve all audio to base64
                with tracer.start_as_current_span("audio-lang-detection.resolve_audio_files") as resolve_span:
                    audio_files_b64: List[Optional[str]] = []
                    for audio_item in request.audio:
                        resolved = self._resolve_audio_base64(audio_item)
                        audio_files_b64.append(resolved)
                    resolved_count = sum(1 for a in audio_files_b64 if a)
                    resolve_span.set_attribute("audio-lang-detection.resolved_count", resolved_count)

                output_list: List[AudioLangDetectionOutput] = []

                # Process each audio input
                for idx, audio_item in enumerate(request.audio):
                    audio_base64 = audio_files_b64[idx]

                    if not audio_base64:
                        output_list.append(self._empty_output())
                        continue

                    with tracer.start_as_current_span("audio-lang-detection.triton_inference") as inference_span:
                        inference_span.set_attribute("audio-lang-detection.audio_index", idx)
                        try:
                            detection_data = self.triton_client.run_audio_lang_detection_inference(
                                audio_base64, model_name=self.model_name
                            )

                            if not detection_data:
                                output_list.append(self._empty_output())
                                continue

                            all_scores_data = detection_data.get("all_scores", {})
                            language_code = detection_data.get("language_code", "")
                            confidence = detection_data.get("confidence", 0.0)

                            inference_span.set_attribute("audio-lang-detection.detected_language", language_code)
                            inference_span.set_attribute("audio-lang-detection.confidence", confidence)

                            output = AudioLangDetectionOutput(
                                language_code=language_code,
                                confidence=confidence,
                                all_scores=AllScores(
                                    predicted_language=all_scores_data.get("predicted_language", ""),
                                    confidence=all_scores_data.get("confidence", 0.0),
                                    top_scores=all_scores_data.get("top_scores", []),
                                ),
                            )
                            output_list.append(output)

                            # Persist result
                            if request_id:
                                try:
                                    await self.repository.create_result(
                                        request_id=request_id,
                                        language_code=language_code,
                                        confidence=confidence,
                                        all_scores=all_scores_data,
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to create result record: {e}")

                        except TritonInferenceError as exc:
                            inference_span.set_attribute("error", True)
                            inference_span.set_attribute("error.type", "TritonInferenceError")
                            inference_span.set_attribute("error.message", str(exc))
                            inference_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            inference_span.record_exception(exc)
                            logger.error("Audio Language Detection Triton inference failed: %s", exc)
                            has_errors = True
                            output_list.append(self._empty_output())

                        except Exception as exc:
                            inference_span.set_attribute("error", True)
                            inference_span.set_attribute("error.type", type(exc).__name__)
                            inference_span.set_attribute("error.message", str(exc))
                            inference_span.set_status(Status(StatusCode.ERROR, str(exc)))
                            inference_span.record_exception(exc)
                            logger.error("Error in audio language detection inference: %s", exc, exc_info=True)
                            has_errors = True
                            output_list.append(self._empty_output())

                # Update request status
                if request_id:
                    try:
                        processing_time = time.time() - start_time
                        status_str = "failed" if has_errors else "completed"
                        span.set_attribute("audio-lang-detection.processing_time_seconds", processing_time)
                        span.set_attribute("audio-lang-detection.status", status_str)
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status=status_str,
                            processing_time=processing_time,
                        )
                    except Exception as e:
                        logger.error(f"Failed to update request status: {e}")

                # Create response config
                response_config = None
                if request.config.serviceId:
                    response_config = AudioLangDetectionResponseConfig(
                        serviceId=request.config.serviceId,
                    )

                span.set_attribute("audio-lang-detection.output_count", len(output_list))
                span.set_attribute("audio-lang-detection.has_errors", has_errors)

                return AudioLangDetectionInferenceResponse(
                    taskType="audio-lang-detection",
                    output=output_list,
                    config=response_config,
                )

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                logger.error(f"Audio language detection inference failed: {e}")

                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                raise
