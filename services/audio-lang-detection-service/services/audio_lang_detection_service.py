"""
Core business logic for Audio Language Detection inference.

This mirrors the behavior of Dhruva's /services/inference/audio-lang-detection
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
from repositories.audio_lang_detection_repository import AudioLangDetectionRepository
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
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

    def __init__(self, triton_client: TritonClient, repository: Optional[AudioLangDetectionRepository] = None):
        self.triton_client = triton_client
        self.repository = repository

    def _resolve_audio_base64(self, audio: AudioInput) -> Optional[str]:
        """
        Resolve an audio into base64:

        - If audioContent is provided, use it directly
        - Else, download from audioUri and base64-encode it
        """
        if not tracer:
            # Fallback if tracing not available
            return self._resolve_audio_base64_impl(audio)
        
        with tracer.start_as_current_span("audio-lang-detection.resolve_audio") as span:
            if audio.audioContent:
                span.set_attribute("audio-lang-detection.audio_source", "content")
                span.set_attribute("audio-lang-detection.audio_size_bytes", len(audio.audioContent) if audio.audioContent else 0)
                span.add_event("audio-lang-detection.audio.resolved", {"source": "content"})
                return audio.audioContent

            if audio.audioUri:
                span.set_attribute("audio-lang-detection.audio_source", "uri")
                span.set_attribute("audio-lang-detection.audio_uri", str(audio.audioUri))
                try:
                    span.add_event("audio-lang-detection.audio.download.start", {"uri": str(audio.audioUri)})
                    resp = requests.get(str(audio.audioUri), timeout=300)
                    resp.raise_for_status()
                    audio_bytes = base64.b64encode(resp.content).decode("utf-8")
                    span.set_attribute("audio-lang-detection.audio_size_bytes", len(audio_bytes))
                    span.set_attribute("audio-lang-detection.download_status", "success")
                    span.add_event("audio-lang-detection.audio.download.complete", {
                        "size_bytes": len(audio_bytes),
                        "status": "success"
                    })
                    return audio_bytes
                except Exception as exc:
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.set_attribute("audio-lang-detection.download_status", "failed")
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    logger.error(
                        "Failed to download audio from %s: %s", audio.audioUri, exc
                    )
                    return None

            # No content and no URI
            span.set_attribute("audio-lang-detection.audio_source", "none")
            span.set_attribute("error", True)
            span.set_attribute("error.message", "No audio content or URI provided")
            return None

    def _resolve_audio_base64_impl(self, audio: AudioInput) -> Optional[str]:
        """Fallback implementation when tracing is not available."""
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
        request: AudioLangDetectionInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> AudioLangDetectionInferenceResponse:
        """
        Asynchronous audio language detection inference entrypoint.
        
        Persists request and results to database if repository is available.
        """
        if not tracer:
            # Fallback if tracing not available
            return await self._run_inference_impl(request, user_id, api_key_id, session_id)
        
        with tracer.start_as_current_span("audio-lang-detection.process_batch") as span:
            span.set_attribute("audio-lang-detection.total_audio", len(request.audio))
            
            start_time = time.time()
            request_id: Optional[UUID] = None
            has_errors = False
            
            # Create request record if repository is available
            if self.repository:
                try:
                    model_id = request.config.serviceId if request.config else None
                    if not model_id:
                        raise ValueError("config.serviceId is required and must be resolved via Model Management")
                    audio_duration = None  # Could be calculated from audio data if needed
                    
                    request_record = await self.repository.create_request(
                        model_id=model_id,
                        audio_duration=audio_duration,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id
                    )
                    request_id = request_record.id
                    span.set_attribute("audio-lang-detection.request_id", str(request_id))
                    logger.info(f"Created audio language detection request {request_id}")
                except Exception as e:
                    logger.error(f"Failed to create request record: {e}")
                    # Continue without persistence
            
            # Resolve all audio to base64 first
            with tracer.start_as_current_span("audio-lang-detection.resolve_audio_files") as resolve_span:
                audio_files_b64: List[Optional[str]] = []
                resolved_count = 0
                for idx, audio_item in enumerate(request.audio):
                    resolved = self._resolve_audio_base64(audio_item)
                    audio_files_b64.append(resolved)
                    if resolved:
                        resolved_count += 1
                resolve_span.set_attribute("audio-lang-detection.resolved_count", resolved_count)
                resolve_span.set_attribute("audio-lang-detection.failed_count", len(request.audio) - resolved_count)

            output_list: List[AudioLangDetectionOutput] = []

            # Process each audio input
            for idx, audio_item in enumerate(request.audio):
                audio_base64 = audio_files_b64[idx]
                
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
                with tracer.start_as_current_span("audio-lang-detection.triton_inference") as inference_span:
                    inference_span.set_attribute("audio-lang-detection.audio_index", idx)
                    try:
                        detection_data = self.triton_client.run_audio_lang_detection_inference(
                            audio_base64
                        )

                        if not detection_data:
                            # Empty response from Triton
                            inference_span.set_attribute("audio-lang-detection.triton_response", "empty")
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
                        
                        # Persist result if repository is available
                        if self.repository and request_id:
                            try:
                                await self.repository.create_result(
                                    request_id=request_id,
                                    language_code=language_code,
                                    confidence=confidence,
                                    all_scores=all_scores_data
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
                        inference_span.set_attribute("error", True)
                        inference_span.set_attribute("error.type", type(exc).__name__)
                        inference_span.set_attribute("error.message", str(exc))
                        inference_span.set_status(Status(StatusCode.ERROR, str(exc)))
                        inference_span.record_exception(exc)
                        logger.error(
                            "Error in audio language detection inference: %s", exc, exc_info=True
                        )
                        has_errors = True
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

            # Update request status if repository is available
            if self.repository and request_id:
                try:
                    processing_time = time.time() - start_time
                    status_str = "failed" if has_errors else "completed"
                    span.set_attribute("audio-lang-detection.processing_time_seconds", processing_time)
                    span.set_attribute("audio-lang-detection.status", status_str)
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status=status_str,
                        processing_time=processing_time
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

    async def _run_inference_impl(
        self, 
        request: AudioLangDetectionInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> AudioLangDetectionInferenceResponse:
        """Fallback implementation when tracing is not available."""
        start_time = time.time()
        request_id: Optional[UUID] = None
        has_errors = False
        
        # Create request record if repository is available
        if self.repository:
            try:
                model_id = request.config.serviceId if request.config else None
                if not model_id:
                    raise ValueError("config.serviceId is required and must be resolved via Model Management")
                audio_duration = None  # Could be calculated from audio data if needed
                
                request_record = await self.repository.create_request(
                    model_id=model_id,
                    audio_duration=audio_duration,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id
                )
                request_id = request_record.id
                logger.info(f"Created audio language detection request {request_id}")
            except Exception as e:
                logger.error(f"Failed to create request record: {e}")
                # Continue without persistence
        
        output_list: List[AudioLangDetectionOutput] = []

        # Process each audio input
        for audio_item in request.audio:
            # Resolve audio to base64
            audio_base64 = self._resolve_audio_base64_impl(audio_item)

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
                output = AudioLangDetectionOutput(
                    language_code=detection_data.get("language_code", ""),
                    confidence=detection_data.get("confidence", 0.0),
                    all_scores=AllScores(
                        predicted_language=all_scores_data.get("predicted_language", ""),
                        confidence=all_scores_data.get("confidence", 0.0),
                        top_scores=all_scores_data.get("top_scores", []),
                    ),
                )
                output_list.append(output)
                
                # Persist result if repository is available
                if self.repository and request_id:
                    try:
                        await self.repository.create_result(
                            request_id=request_id,
                            language_code=detection_data.get("language_code", ""),
                            confidence=detection_data.get("confidence", 0.0),
                            all_scores=all_scores_data
                        )
                    except Exception as e:
                        logger.error(f"Failed to create result record: {e}")

            except TritonInferenceError as exc:
                logger.error("Audio Language Detection Triton inference failed: %s", exc)
                has_errors = True
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
                has_errors = True
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

        # Update request status if repository is available
        if self.repository and request_id:
            try:
                processing_time = time.time() - start_time
                status_str = "failed" if has_errors else "completed"
                await self.repository.update_request_status(
                    request_id=request_id,
                    status=status_str,
                    processing_time=processing_time
                )
            except Exception as e:
                logger.error(f"Failed to update request status: {e}")

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

