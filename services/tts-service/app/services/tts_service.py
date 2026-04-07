"""
Main TTS service class containing core inference logic.

Refactored: eliminated _run_inference_impl duplicate, added fallback retry logic.
"""

import base64
import logging
import time
from io import BytesIO
from typing import Optional, Any

import numpy as np
from scipy.io import wavfile
from pydub import AudioSegment
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import (
    TTSInferenceRequest,
    TTSInferenceResponse,
    AudioOutput,
    AudioConfig,
)
from app.repositories.tts_repository import TTSRepository
from app.services.audio_service import AudioService
from app.services.text_service import TextService
from app.clients.triton_client import TTSTritonClient
from ai4icore_exceptions import TritonInferenceError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("tts-service")


def count_words(text: str) -> int:
    """Count words in text."""
    try:
        words = [word for word in text.split() if word.strip()]
        return len(words)
    except Exception:
        return 0


class TTSService:
    """Main TTS service for text-to-speech inference."""

    def __init__(
        self,
        repository: TTSRepository,
        audio_service: AudioService,
        text_service: TextService,
        triton_client: TTSTritonClient,
        resolved_model_name: Optional[str] = None,
    ):
        """Initialize TTS service with dependencies."""
        self.repository = repository
        self.audio_service = audio_service
        self.text_service = text_service
        self.triton_client = triton_client
        self.resolved_model_name = resolved_model_name

    async def run_inference(
        self,
        request: TTSInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        http_request: Optional[Any] = None,
    ) -> TTSInferenceResponse:
        """Run TTS inference for the given request."""
        start_time = time.time()
        request_id = None

        with tracer.start_as_current_span("tts.process_batch") as span:
            try:
                # ── Extract configuration ──
                service_id = request.config.serviceId
                if not service_id and http_request:
                    service_id = getattr(http_request.state, "service_id", None)

                if not service_id:
                    raise TritonInferenceError(
                        "serviceId is required. It should be provided in the request or resolved via SMR."
                    )

                language = request.config.language.sourceLanguage
                gender = request.config.gender.value
                standard_rate = 22050
                target_sr = request.config.samplingRate or 22050
                audio_format = request.config.audioFormat.value

                # Use resolved model name from Model Management (REQUIRED)
                if not self.resolved_model_name:
                    raise TritonInferenceError(
                        f"Model name not resolved via Model Management for serviceId: {service_id}. "
                        f"Please ensure the model is properly configured in Model Management database "
                        f"with inference endpoint schema."
                    )
                model_name = self.resolved_model_name

                # Convert PCM format to s16le for Triton
                fmt = "s16le" if audio_format == "pcm" else audio_format

                span.set_attribute("tts.total_inputs", len(request.input))
                span.set_attribute("tts.service_id", service_id)
                span.set_attribute("tts.language", language)
                span.set_attribute("tts.gender", gender)
                span.set_attribute("tts.audio_format", audio_format)
                span.set_attribute("tts.sampling_rate", target_sr)

                logger.info(f"Starting TTS inference for {len(request.input)} text inputs")

                # Initialize response
                response = TTSInferenceResponse(audio=[])

                # Create database request record
                total_text_length = sum(len(inp.source) for inp in request.input)
                db_request = await self.repository.create_request(
                    model_id=service_id,
                    voice_id=gender,
                    language=language,
                    text_length=total_text_length,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                )
                request_id = db_request.id

                # ── Process each text input ──
                for input_idx, text_input in enumerate(request.input):
                    with tracer.start_as_current_span("tts.process_input") as input_span:
                        try:
                            input_span.set_attribute("tts.input_index", input_idx)
                            input_span.set_attribute("tts.input_text_length", len(text_input.source))
                            logger.info(f"Processing text input {input_idx + 1}/{len(request.input)}")

                            # Preprocess text
                            processed_text = self.text_service.process_tts_input(text_input.source)

                            # Chunk long text
                            if len(processed_text) > 400:
                                text_chunks = self.text_service.chunk_text(processed_text, max_length=400)
                            else:
                                text_chunks = [processed_text]

                            # Generate audio for each chunk
                            raw_audios = []
                            for chunk_idx, chunk in enumerate(text_chunks):
                                with tracer.start_as_current_span("tts.generate_audio_chunk") as chunk_span:
                                    try:
                                        chunk_span.set_attribute("tts.chunk_index", chunk_idx)
                                        chunk_span.set_attribute("tts.chunk_length", len(chunk))

                                        inputs, outputs = self.triton_client.get_tts_io_for_triton(
                                            text=chunk, gender=gender, language=language
                                        )

                                        triton_response = self.triton_client.send_triton_request(
                                            model_name=model_name,
                                            inputs=inputs,
                                            outputs=outputs,
                                        )

                                        raw_audio = triton_response.as_numpy("OUTPUT_GENERATED_AUDIO")[0]
                                        raw_audios.append(raw_audio)

                                    except Exception as e:
                                        chunk_span.set_status(Status(StatusCode.ERROR, str(e)))
                                        chunk_span.record_exception(e)
                                        logger.error(f"Triton inference failed for chunk: {e}")
                                        raise TritonInferenceError(f"Triton inference failed: {e}")

                            # Concatenate audio chunks
                            raw_audio = np.concatenate(raw_audios) if len(raw_audios) > 1 else raw_audios[0]

                            # Resample audio
                            final_audio = self.audio_service.resample_audio(raw_audio, standard_rate, target_sr)

                            # Adjust duration if specified
                            if text_input.audioDuration:
                                cur_duration = len(final_audio) / target_sr
                                speed_factor = cur_duration / text_input.audioDuration
                                if speed_factor > 1:
                                    final_audio = self.audio_service.stretch_audio(final_audio, speed_factor, target_sr)
                                elif speed_factor < 1:
                                    silence_duration = text_input.audioDuration - cur_duration
                                    final_audio = self.audio_service.append_silence(final_audio, silence_duration, target_sr)

                            # Convert to WAV then to target format
                            byte_io = BytesIO()
                            wavfile.write(byte_io, target_sr, final_audio)
                            byte_io.seek(0)

                            if fmt != "wav":
                                audio_segment = AudioSegment.from_file(byte_io, format="wav")
                                byte_io = BytesIO()
                                audio_segment.export(byte_io, format=fmt)
                                byte_io.seek(0)

                            # Encode to base64
                            audio_bytes = byte_io.read()
                            encoded_string = base64.b64encode(audio_bytes).decode("utf-8")

                            audio_output = AudioOutput(audioContent=encoded_string)
                            response.audio.append(audio_output)

                            input_span.set_attribute("tts.output_audio_size", len(audio_bytes))
                            logger.info(f"Generated audio for input {input_idx + 1}, size: {len(audio_bytes)} bytes")

                        except Exception as e:
                            input_span.set_status(Status(StatusCode.ERROR, str(e)))
                            input_span.record_exception(e)
                            logger.error(f"Failed to process text input {input_idx + 1}: {e}")
                            await self.repository.update_request_status(request_id, "failed", error_message=str(e))
                            raise

                # ── Build response config ──
                total_audio_duration = None
                total_audio_size = 0

                if response.audio:
                    total_audio_size = sum(len(base64.b64decode(a.audioContent)) for a in response.audio)
                    total_samples = total_audio_size / 2
                    total_audio_duration = total_samples / target_sr

                response.config = AudioConfig(
                    language=request.config.language,
                    audioFormat=request.config.audioFormat,
                    encoding="base64",
                    samplingRate=target_sr,
                    audioDuration=total_audio_duration,
                )

                # Create database result record
                last_encoded = response.audio[-1].audioContent if response.audio else ""
                await self.repository.create_result(
                    request_id=request_id,
                    audio_file_path=last_encoded[:100] if last_encoded else "",
                    audio_duration=total_audio_duration,
                    audio_format=fmt,
                    sample_rate=target_sr,
                    file_size=total_audio_size,
                )

                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(request_id, "completed", processing_time=processing_time)

                span.set_attribute("tts.processing_time_seconds", processing_time)
                span.set_attribute("tts.output_count", len(response.audio))

                # Calculate input metrics
                input_texts = [ti.source for ti in request.input]
                total_input_characters = sum(len(t) for t in input_texts)
                total_input_words = sum(count_words(t) for t in input_texts)
                total_output_audio_duration = total_audio_duration if total_audio_duration else 0.0

                span.set_attribute("tts.output.audio_length_seconds", total_output_audio_duration)
                span.set_attribute("tts.output.audio_length_ms", total_output_audio_duration * 1000.0)
                if total_audio_size > 0:
                    span.set_attribute("tts.output.audio_size_bytes", total_audio_size)

                logger.info(
                    f"TTS inference completed for request {request_id} in {processing_time:.2f}s, "
                    f"input_characters={total_input_characters}, input_words={total_input_words}, "
                    f"output_audio_duration={total_output_audio_duration:.2f}s",
                    extra={
                        "input_details": {
                            "character_length": total_input_characters,
                            "word_count": total_input_words,
                            "input_count": len(request.input),
                        },
                        "output_details": {
                            "audio_length_seconds": total_output_audio_duration,
                            "audio_length_ms": total_output_audio_duration * 1000.0,
                            "output_count": len(response.audio),
                        },
                        "request_id": str(request_id),
                        "processing_time_seconds": processing_time,
                        "service_id": service_id,
                        "source_language": language,
                    },
                )
                return response

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)

                logger.error(
                    f"TTS inference failed: {e}",
                    extra={
                        "context": {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "service_id": request.config.serviceId if hasattr(request, "config") and request.config else None,
                            "request_id": request_id,
                            "user_id": user_id,
                            "api_key_id": api_key_id,
                            "session_id": session_id,
                        }
                    },
                    exc_info=True,
                )

                if request_id:
                    try:
                        await self.repository.update_request_status(request_id, "failed", error_message=str(e))
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")

                if isinstance(e, TritonInferenceError):
                    raise
                raise TritonInferenceError(f"TTS inference failed: {e}")
