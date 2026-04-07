"""
Main ASR service class containing core inference logic.

Refactored version with fallback retry support and clean imports.
"""

import asyncio
import base64
import json
import logging
import time
from contextlib import nullcontext
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import soundfile as sf
from fastapi import Request

from app.schemas.inference import (
    ASRInferenceRequest,
    ASRInferenceResponse,
    TranscriptOutput,
    NBestToken,
)
from app.repositories.asr_repository import ASRRepository
from app.services.audio_service import AudioService
from app.clients.triton_client import ASRTritonClient
from ai4icore_exceptions import TritonInferenceError

# OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None

logger = logging.getLogger(__name__)

# Get tracer for manual span creation
tracer = None
if TRACING_AVAILABLE and trace:
    try:
        tracer = trace.get_tracer("asr-service")
    except Exception:
        tracer = None


def count_words(text: str) -> int:
    """Count words in text."""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0


class ASRService:
    """Main ASR service for speech-to-text conversion."""

    def __init__(
        self,
        repository: ASRRepository,
        audio_service: AudioService,
        triton_client: ASRTritonClient,
        resolved_model_name: Optional[str] = None,
    ):
        """Initialize ASR service with dependencies."""
        self.repository = repository
        self.audio_service = audio_service
        self.triton_client = triton_client
        self.resolved_model_name = resolved_model_name  # Model name from Model Management

    async def run_inference(
        self,
        request: ASRInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        http_request: Optional[Request] = None,
        http_request_state: Optional[Any] = None,
    ) -> ASRInferenceResponse:
        """Run ASR inference on audio inputs.

        When *http_request* is provided and a fallback service ID exists on the
        request state, the method will automatically retry with the fallback
        service on ``TritonInferenceError``.
        """
        start_time = time.time()

        # Allow callers to pass the state object directly (legacy compat)
        _state = http_request_state or (http_request.state if http_request else None)

        try:
            return await self._run_inference_impl(
                request,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id,
                http_request_state=_state,
                start_time=start_time,
            )

        except (TritonInferenceError, Exception) as primary_error:
            # --- Fallback retry logic ---
            if not http_request:
                raise

            fallback_service_id = getattr(_state, "fallback_service_id", None)
            original_service_id = request.config.serviceId

            if not fallback_service_id or fallback_service_id == original_service_id:
                raise

            logger.warning(
                "ASR: Primary service failed, attempting fallback",
                extra={
                    "primary_service_id": original_service_id,
                    "fallback_service_id": fallback_service_id,
                    "error_type": type(primary_error).__name__,
                    "error_message": str(primary_error),
                },
                exc_info=True,
            )

            try:
                from app.services.smr_service import SMRService

                smr_svc = SMRService()
                triton_endpoint, triton_api_key, triton_model_name = await smr_svc.switch_to_fallback(
                    request=request,
                    http_request=http_request,
                    fallback_service_id=fallback_service_id,
                )

                # Strip scheme for TritonClient
                triton_url = triton_endpoint
                if triton_url.startswith(("http://", "https://")):
                    triton_url = triton_url.split("://", 1)[1]

                from app.repositories.asr_repository import ASRRepository as _Repo
                from app.services.audio_service import AudioService as _Audio
                from app.clients.triton_client import ASRTritonClient as _Triton

                from ai4icore_multi_tenant import get_tenant_db_session_factory

                _get_session = get_tenant_db_session_factory()
                fallback_db = await _get_session(http_request)

                fallback_service = ASRService(
                    repository=_Repo(fallback_db),
                    audio_service=_Audio(),
                    triton_client=_Triton(triton_url, api_key=triton_api_key or None),
                    resolved_model_name=triton_model_name,
                )

                response = await fallback_service._run_inference_impl(
                    request,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                    http_request_state=http_request.state,
                    start_time=time.time(),
                )

                logger.info(
                    "ASR: Fallback service succeeded",
                    extra={"fallback_service_id": fallback_service_id},
                )
                return response

            except Exception as fallback_error:
                logger.error(
                    "ASR: Both primary and fallback services failed",
                    extra={
                        "primary_service_id": original_service_id,
                        "fallback_service_id": fallback_service_id,
                        "primary_error": str(primary_error),
                        "fallback_error": str(fallback_error),
                    },
                    exc_info=True,
                )

                raise TritonInferenceError(
                    f"Primary service ({original_service_id}) failed: {primary_error}. "
                    f"Fallback service ({fallback_service_id}) also failed: {fallback_error}"
                ) from fallback_error

    # ------------------------------------------------------------------
    # Core inference implementation (single attempt)
    # ------------------------------------------------------------------

    async def _run_inference_impl(
        self,
        request: ASRInferenceRequest,
        *,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        http_request_state: Optional[Any] = None,
        start_time: float,
    ) -> ASRInferenceResponse:
        """Internal inference logic -- no fallback retry."""
        service_id = request.config.serviceId
        if not service_id and http_request_state:
            service_id = getattr(http_request_state, "service_id", None)

        if not service_id:
            raise TritonInferenceError(
                "serviceId is required. It should be provided in the request or resolved via SMR."
            )

        language = request.config.language.sourceLanguage
        pre_processors = request.config.preProcessors or []
        post_processors = request.config.postProcessors or []
        transcription_format = request.config.transcriptionFormat
        best_token_count = request.config.bestTokenCount

        # Validate language code
        from app.utils.validation_utils import SUPPORTED_LANGUAGES, InvalidLanguageCodeError

        if language not in SUPPORTED_LANGUAGES:
            raise InvalidLanguageCodeError(
                f"Language '{language}' is not supported by the IndicASR model. "
                f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}. "
                f"Note: English ('en') is not supported by this Indic language ASR model."
            )

        # Use resolved model name from Model Management (REQUIRED)
        if not self.resolved_model_name:
            raise TritonInferenceError(
                f"Model name not resolved via Model Management for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            )
        model_name = self.resolved_model_name
        standard_rate = 16000

        model_id_for_db = service_id
        if not model_id_for_db:
            raise TritonInferenceError(
                "Cannot create database record: serviceId is missing. "
                "Please ensure serviceId is provided in the request or resolved via SMR."
            )

        # Create database request record
        db_request = await self.repository.create_request(
            model_id=model_id_for_db,
            language=language,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
        )

        logger.info(f"Created ASR request {db_request.id} for {len(request.audio)} audio inputs")

        # Initialize response
        response = ASRInferenceResponse(output=[])

        # Process each audio input
        for audio_idx, audio_input in enumerate(request.audio):
            try:
                logger.info(f"Processing audio input {audio_idx + 1}/{len(request.audio)}")

                span_ctx = tracer.start_as_current_span("asr.process_audio_input") if tracer else nullcontext()
                with span_ctx as audio_span:
                    if audio_span:
                        audio_span.set_attribute("asr.audio_index", audio_idx + 1)
                        audio_span.set_attribute("asr.total_audio_count", len(request.audio))

                    # Get audio bytes
                    audio_bytes = await self._get_audio_bytes(audio_input)

                    # Process audio
                    file_handle = BytesIO(audio_bytes)
                    processed_audio = await self._process_audio_input(file_handle, standard_rate)

                    # Run preprocessors
                    audio_chunks, speech_timestamps = await self._run_asr_pre_processors(
                        processed_audio, pre_processors, standard_rate
                    )

                    # Batch inference
                    transcript_lines = []
                    n_best_tokens = []
                    batch_size = 32 if "whisper" not in service_id.lower() else 1

                    for i in range(0, len(audio_chunks), batch_size):
                        batch = audio_chunks[i : i + batch_size]

                        inputs, outputs = self.triton_client.get_asr_io_for_triton(
                            batch, service_id, language, best_token_count
                        )

                        triton_response = self.triton_client.send_triton_request(
                            model_name, inputs, outputs
                        )

                        transcripts = triton_response.as_numpy("TRANSCRIPTS")

                        if transcripts is None:
                            logger.error(
                                f"Triton returned None for TRANSCRIPTS output (batch {i // batch_size + 1}, audio {audio_idx + 1})"
                            )
                            raise TritonInferenceError("Triton returned None for TRANSCRIPTS output")

                        # Handle both 1D and 2D arrays
                        if isinstance(transcripts, np.ndarray) and transcripts.ndim == 2:
                            if transcripts.shape[1] == 1:
                                transcripts_flat = [transcripts[j, 0] for j in range(transcripts.shape[0])]
                            else:
                                transcripts_flat = [
                                    transcripts[j, 0] if transcripts.shape[1] > 0 else b""
                                    for j in range(transcripts.shape[0])
                                ]
                        elif isinstance(transcripts, np.ndarray) and transcripts.ndim == 1:
                            transcripts_flat = transcripts
                        else:
                            transcripts_flat = transcripts

                        for j, transcript_bytes in enumerate(transcripts_flat):
                            try:
                                transcript_text = self._decode_transcript(transcript_bytes)

                                if not transcript_text or not transcript_text.strip():
                                    continue

                                if best_token_count > 0:
                                    try:
                                        transcript_data = json.loads(transcript_text)
                                        transcript_text = transcript_data.get("source", transcript_text)
                                        if "nBestTokens" in transcript_data:
                                            n_best_tokens.extend(transcript_data["nBestTokens"])
                                    except json.JSONDecodeError:
                                        pass

                                # Add timestamp if available
                                if i + j < len(speech_timestamps):
                                    timestamp = speech_timestamps[i + j]
                                    transcript_lines.append({
                                        "text": transcript_text,
                                        "start": timestamp.get("start_secs", 0),
                                        "end": timestamp.get("end_secs", 0),
                                    })
                                else:
                                    transcript_lines.append({"text": transcript_text, "start": 0, "end": 0})

                            except Exception as decode_error:
                                logger.error(f"Failed to decode transcript at batch {i // batch_size + 1}, position {j}: {decode_error}", exc_info=True)
                                continue

                    if not transcript_lines:
                        raise TritonInferenceError(
                            f"No transcripts extracted from Triton for audio input {audio_idx + 1}. "
                            f"Triton may have returned empty results. Please check the model and audio input."
                        )

                    # Run postprocessors
                    processed_transcript_lines = await self._run_asr_post_processors(
                        transcript_lines, post_processors, language
                    )

                    if not processed_transcript_lines:
                        raise TritonInferenceError(
                            f"Postprocessing resulted in empty transcripts for audio input {audio_idx + 1}"
                        )

                # Format response
                transcript = self._create_asr_response_format(processed_transcript_lines, transcription_format)

                if not transcript or not transcript.strip():
                    raise TritonInferenceError(
                        f"Formatted transcript is empty for audio input {audio_idx + 1}"
                    )

                n_best_tokens_list = None
                if n_best_tokens:
                    n_best_tokens_list = [
                        NBestToken(word=token.get("word", ""), tokens=token.get("tokens", []))
                        for token in n_best_tokens
                    ]

                transcript_output = TranscriptOutput(source=transcript, nBestTokens=n_best_tokens_list)
                response.output.append(transcript_output)

                # Create database result record
                await self.repository.create_result(
                    request_id=db_request.id,
                    transcript=transcript,
                    confidence_score=None,
                    word_timestamps=[line for line in processed_transcript_lines if "start" in line],
                    language_detected=language,
                    audio_format=request.config.audioFormat.value if request.config.audioFormat else None,
                    sample_rate=standard_rate,
                )

                logger.info(f"Completed processing audio input {audio_idx + 1}")

            except Exception as e:
                logger.error(
                    f"Failed to process audio input {audio_idx + 1}: {e}",
                    extra={
                        "audio_index": audio_idx + 1,
                        "error_type": type(e).__name__,
                        "service_id": service_id,
                    },
                    exc_info=True,
                )
                raise TritonInferenceError(
                    f"Failed to process audio input {audio_idx + 1}: {e}"
                ) from e

        # Update request status
        processing_time = time.time() - start_time
        await self.repository.update_request_status(db_request.id, "completed", processing_time)

        logger.info(f"Completed ASR inference in {processing_time:.2f}s")
        return response

    # ------------------------------------------------------------------
    # Audio helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_transcript(transcript_bytes) -> str:
        """Decode a single transcript value from Triton into a string."""
        if isinstance(transcript_bytes, bytes):
            return transcript_bytes.decode("utf-8")
        if isinstance(transcript_bytes, np.ndarray):
            if transcript_bytes.dtype == object:
                return str(transcript_bytes.item())
            if transcript_bytes.size > 0:
                if transcript_bytes.dtype == np.uint8:
                    return transcript_bytes.tobytes().decode("utf-8")
                return str(transcript_bytes.item())
            return ""
        if isinstance(transcript_bytes, (str, np.str_)):
            return str(transcript_bytes)
        return str(transcript_bytes)

    async def _get_audio_bytes(self, audio_input) -> bytes:
        """Extract audio bytes from AudioInput."""
        from app.utils.validation_utils import UploadFailedError, UploadTimeoutError, NoFileSelectedError

        try:
            if audio_input.audioContent:
                return base64.b64decode(audio_input.audioContent)
            elif audio_input.audioUri:
                return await self.audio_service.download_audio(str(audio_input.audioUri))
            else:
                raise NoFileSelectedError("No audio content or URI provided")
        except (UploadFailedError, UploadTimeoutError, NoFileSelectedError):
            raise
        except Exception as e:
            logger.error(f"Failed to get audio bytes: {e}")
            raise UploadFailedError("File upload failed. Please check your internet connection and try again.")

    async def _process_audio_input(self, file_handle: BytesIO, target_rate: int) -> np.ndarray:
        """Process audio input through preprocessing pipeline."""
        from ai4icore_exceptions import AudioProcessingError

        try:
            try:
                audio_data, sample_rate = sf.read(file_handle)
            except Exception as sf_error:
                logger.warning(f"soundfile failed to read audio: {sf_error}, trying pydub")
                file_handle.seek(0)
                from pydub import AudioSegment

                audio_segment = AudioSegment.from_file(file_handle)
                sample_rate = audio_segment.frame_rate
                audio_data = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
                audio_data = audio_data / (2**15)
                if audio_segment.channels == 2:
                    audio_data = audio_data.reshape((-1, 2))

            audio_mono = self.audio_service.stereo_to_mono(audio_data)
            audio_resampled = self.audio_service.resample_audio(audio_mono, sample_rate, target_rate)
            audio_segment = self.audio_service.equalize_amplitude(audio_resampled, target_rate)
            final_audio = self.audio_service.dequantize_audio(audio_segment)
            return final_audio

        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            raise AudioProcessingError(f"Audio processing failed: {e}")

    async def _run_asr_pre_processors(
        self,
        audio: np.ndarray,
        pre_processors: List[str],
        sample_rate: int,
    ) -> Tuple[List[np.ndarray], List[Dict[str, float]]]:
        """Run audio preprocessing."""
        if "vad" in pre_processors:
            return await self.audio_service.silero_vad_chunking(
                audio, sample_rate, triton_client=self.triton_client
            )
        return [audio], [{"start": 0, "end": len(audio), "start_secs": 0, "end_secs": len(audio) / sample_rate}]

    async def _run_asr_post_processors(
        self,
        transcript_lines: List[Dict[str, Any]],
        post_processors: List[str],
        language: str,
    ) -> List[Dict[str, Any]]:
        """Run text postprocessing."""
        # TODO: Implement ITN and punctuation postprocessors
        return transcript_lines

    def _create_asr_response_format(
        self,
        transcript_lines: List[Dict[str, Any]],
        transcription_format: str,
    ) -> str:
        """Format transcript based on requested format."""
        if transcription_format == "srt":
            return self._format_as_srt(transcript_lines)
        elif transcription_format == "webvtt":
            return self._format_as_webvtt(transcript_lines)
        return " ".join([line["text"] for line in transcript_lines])

    def _format_as_srt(self, transcript_lines: List[Dict[str, Any]]) -> str:
        """Format transcript as SRT subtitles."""
        srt_content = []
        for i, line in enumerate(transcript_lines, 1):
            start_time = self._format_timestamp(line.get("start", 0))
            end_time = self._format_timestamp(line.get("end", 0))
            srt_content.append(f"{i}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(line["text"])
            srt_content.append("")
        return "\n".join(srt_content)

    def _format_as_webvtt(self, transcript_lines: List[Dict[str, Any]]) -> str:
        """Format transcript as WebVTT subtitles."""
        webvtt_content = ["WEBVTT", ""]
        for line in transcript_lines:
            start_time = self._format_webvtt_timestamp(line.get("start", 0))
            end_time = self._format_webvtt_timestamp(line.get("end", 0))
            webvtt_content.append(f"{start_time} --> {end_time}")
            webvtt_content.append(line["text"])
            webvtt_content.append("")
        return "\n".join(webvtt_content)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    @staticmethod
    def _format_webvtt_timestamp(seconds: float) -> str:
        """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"
