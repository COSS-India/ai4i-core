"""
Main TTS service class containing core inference logic.

Refactored: eliminated _run_inference_impl duplicate, added fallback retry logic.
"""

import base64
import logging
import time
from io import BytesIO
from typing import Any, List, Optional

import numpy as np
from scipy.io import wavfile
from pydub import AudioSegment
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
from ai4icore_telemetry import StandardSpanManager, Status, StatusCode

logger = logging.getLogger(__name__)
_standard_spans = StandardSpanManager("tts")


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
        fmt = "s16le" if audio_format == "pcm" else audio_format

        input_count = len(request.input)
        input_texts = [ti.source for ti in request.input]
        total_input_characters = sum(len(t) for t in input_texts)
        total_input_words = sum(count_words(t) for t in input_texts)

        with _standard_spans.inference(
            service_id=service_id,
            model_name=None,
            input_count=input_count,
            input_type="text",
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id,
            extra_attrs={
                "tts.source_language": language,
                "tts.gender": gender,
                "tts.audio_format": audio_format,
                "tts.sampling_rate": target_sr,
                "tts.input.character_length": total_input_characters,
                "tts.input.word_count": total_input_words,
            },
        ) as parent_span:
            try:
                all_chunks: List[List[str]] = []
                with _standard_spans.preprocess() as preprocess_span:
                    preprocess_span.set_attribute("tts.preprocess.modality", "text")
                    preprocess_span.set_attribute(
                        "tts.preprocess.operations_applied",
                        "normalize_tts_input,chunk_text_if_over_limit",
                    )
                    preprocess_span.set_attribute("tts.preprocess.max_chunk_characters", 400)
                    preprocess_span.set_attribute("tts.input_count", input_count)
                    preprocess_span.set_attribute(
                        "tts.input.character_length", total_input_characters
                    )
                    preprocess_span.set_attribute(
                        "tts.input.word_count", total_input_words
                    )
                    preprocess_span.add_event(
                        "tts.preprocess.phase_started",
                        {"input_line_count": input_count},
                    )

                    for input_idx, text_input in enumerate(request.input):
                        t_preprocess = time.perf_counter()
                        processed_text = self.text_service.process_tts_input(
                            text_input.source
                        )
                        if len(processed_text) > 400:
                            chunks = self.text_service.chunk_text(
                                processed_text, max_length=400
                            )
                        else:
                            chunks = [processed_text]
                        all_chunks.append(chunks)
                        preprocess_span.add_event(
                            "tts.preprocess.input_completed",
                            {
                                "input_index": input_idx,
                                "chunk_count": len(chunks),
                                "chunked": len(chunks) > 1,
                                "duration_ms": (time.perf_counter() - t_preprocess)
                                * 1000.0,
                            },
                        )

                with _standard_spans.resolve_model() as resolve_span:
                    if not self.resolved_model_name:
                        raise TritonInferenceError(
                            f"Model name not resolved via Model Management for serviceId: {service_id}. "
                            f"Please ensure the model is properly configured in Model Management database "
                            f"with inference endpoint schema."
                        )
                    model_name = self.resolved_model_name
                    resolve_span.set_attribute(
                        "tts.resolve_model.lookup_service_id", service_id
                    )
                    resolve_span.set_attribute(
                        "tts.resolve_model.registry_model_name", model_name
                    )
                    resolve_span.set_attribute(
                        "tts.resolve_model.resolution_source",
                        "model_management_precached_on_service",
                    )
                    resolve_span.set_attribute(
                        "tts.resolve_model.triton_infer_endpoint",
                        getattr(self.triton_client, "triton_url", "") or "",
                    )
                    resolve_span.set_attribute("tts.resolve_model.triton_client_ready", True)
                    resolve_span.add_event(
                        "tts.resolve_model.completed",
                        {
                            "registry_model_name": model_name,
                            "endpoint_configured": bool(
                                getattr(self.triton_client, "triton_url", None)
                            ),
                        },
                    )
                    if parent_span is not None:
                        try:
                            parent_span.set_attribute("tts.model_name", model_name)
                        except Exception:
                            pass

                total_text_length = sum(len(inp.source) for inp in request.input)

                logger.info(f"Starting TTS inference for {input_count} text inputs")

                all_raw_audios: List[List[np.ndarray]] = [[] for _ in request.input]

                with _standard_spans.triton_inference() as triton_span:
                    total_chunks = sum(len(c) for c in all_chunks)
                    triton_span.set_attribute("tts.triton_inference.task", "synthesis")
                    triton_span.set_attribute(
                        "tts.triton_inference.input_line_count", input_count
                    )
                    triton_span.set_attribute(
                        "tts.triton_inference.chunk_invocation_count", total_chunks
                    )
                    triton_span.set_attribute(
                        "tts.triton_inference.triton_invoke_model_name", model_name
                    )
                    triton_span.set_attribute(
                        "tts.triton_inference.io_schema",
                        "INPUT_TEXT,INPUT_SPEAKER_ID,INPUT_LANGUAGE_ID -> OUTPUT_GENERATED_AUDIO",
                    )
                    triton_span.set_attribute(
                        "tts.triton_inference.source_language", language
                    )
                    triton_span.set_attribute("tts.triton_inference.voice_gender", gender)
                    triton_span.add_event(
                        "tts.triton_inference.phase_started",
                        {
                            "chunk_invocations": total_chunks,
                            "steps": "prepare_io,triton.inference_per_chunk,read_OUTPUT_GENERATED_AUDIO",
                        },
                    )

                    for input_idx, _ in enumerate(request.input):
                        for chunk_idx, chunk in enumerate(all_chunks[input_idx]):
                            t_chunk = time.perf_counter()
                            try:
                                inputs, outputs = (
                                    self.triton_client.get_tts_io_for_triton(
                                        text=chunk,
                                        gender=gender,
                                        language=language,
                                    )
                                )
                                triton_span.add_event(
                                    "tts.triton_inference.prepare_io.completed",
                                    {
                                        "input_index": input_idx,
                                        "chunk_index": chunk_idx,
                                        "input_tensors": "INPUT_TEXT,INPUT_SPEAKER_ID,INPUT_LANGUAGE_ID",
                                        "output_tensors": "OUTPUT_GENERATED_AUDIO",
                                    },
                                )
                                triton_response = self.triton_client.send_triton_request(
                                    model_name=model_name,
                                    inputs=inputs,
                                    outputs=outputs,
                                    trace_attributes={
                                        "triton.parent_phase": "tts.triton_inference",
                                        "triton.loop.input_index": input_idx,
                                        "triton.loop.chunk_index": chunk_idx,
                                        "tts.speaker_id": gender,
                                        "tts.language_id": language,
                                    },
                                )
                                raw_audio = triton_response.as_numpy(
                                    "OUTPUT_GENERATED_AUDIO"
                                )[0]
                                all_raw_audios[input_idx].append(raw_audio)
                                triton_span.add_event(
                                    "tts.triton_inference.chunk_completed",
                                    {
                                        "input_index": input_idx,
                                        "chunk_index": chunk_idx,
                                        "duration_ms": (time.perf_counter() - t_chunk)
                                        * 1000.0,
                                    },
                                )
                            except Exception as e:
                                triton_span.set_status(Status(StatusCode.ERROR, str(e)))
                                triton_span.record_exception(e)
                                logger.error(f"Triton inference failed for chunk: {e}")
                                raise TritonInferenceError(
                                    f"Triton inference failed: {e}"
                                )

                response = TTSInferenceResponse(audio=[])

                with _standard_spans.postprocess() as postprocess_span:
                    postprocess_span.set_attribute("tts.postprocess.modality", "audio")
                    postprocess_span.set_attribute(
                        "tts.postprocess.operations_applied",
                        "concatenate_chunk_waveforms,resample,stretch_or_pad_to_target_duration,wav_write,optional_format_convert,base64_encode",
                    )
                    postprocess_span.set_attribute(
                        "tts.postprocess.internal_sample_rate_hz", standard_rate
                    )
                    postprocess_span.set_attribute(
                        "tts.postprocess.target_sample_rate_hz", target_sr
                    )
                    postprocess_span.set_attribute(
                        "tts.postprocess.response_audio_format", fmt
                    )
                    postprocess_span.set_attribute("tts.input_count", input_count)
                    postprocess_span.add_event(
                        "tts.postprocess.phase_started",
                        {"input_line_count": input_count},
                    )

                    for input_idx, text_input in enumerate(request.input):
                        try:
                            raw_audios = all_raw_audios[input_idx]
                            t0 = time.perf_counter()
                            raw_audio = (
                                np.concatenate(raw_audios)
                                if len(raw_audios) > 1
                                else raw_audios[0]
                            )
                            postprocess_span.add_event(
                                "tts.postprocess.concatenate_completed",
                                {
                                    "input_index": input_idx,
                                    "duration_ms": (time.perf_counter() - t0) * 1000.0,
                                },
                            )

                            t0 = time.perf_counter()
                            final_audio = self.audio_service.resample_audio(
                                raw_audio, standard_rate, target_sr
                            )
                            postprocess_span.add_event(
                                "tts.postprocess.resample_completed",
                                {
                                    "input_index": input_idx,
                                    "duration_ms": (time.perf_counter() - t0) * 1000.0,
                                },
                            )

                            if text_input.audioDuration:
                                t0 = time.perf_counter()
                                cur_duration = len(final_audio) / target_sr
                                speed_factor = (
                                    cur_duration / text_input.audioDuration
                                )
                                if speed_factor > 1:
                                    final_audio = self.audio_service.stretch_audio(
                                        final_audio, speed_factor, target_sr
                                    )
                                elif speed_factor < 1:
                                    silence_duration = (
                                        text_input.audioDuration - cur_duration
                                    )
                                    final_audio = self.audio_service.append_silence(
                                        final_audio, silence_duration, target_sr
                                    )
                                postprocess_span.add_event(
                                    "tts.postprocess.adjust_duration_completed",
                                    {
                                        "input_index": input_idx,
                                        "duration_ms": (time.perf_counter() - t0)
                                        * 1000.0,
                                    },
                                )

                            t0 = time.perf_counter()
                            byte_io = BytesIO()
                            wavfile.write(byte_io, target_sr, final_audio)
                            byte_io.seek(0)

                            if fmt != "wav":
                                audio_segment = AudioSegment.from_file(
                                    byte_io, format="wav"
                                )
                                byte_io = BytesIO()
                                audio_segment.export(byte_io, format=fmt)
                                byte_io.seek(0)

                            audio_bytes = byte_io.read()
                            encoded_string = base64.b64encode(audio_bytes).decode(
                                "utf-8"
                            )
                            postprocess_span.add_event(
                                "tts.postprocess.convert_encode_completed",
                                {
                                    "input_index": input_idx,
                                    "output_audio_size_bytes": len(audio_bytes),
                                    "duration_ms": (time.perf_counter() - t0) * 1000.0,
                                },
                            )

                            audio_output = AudioOutput(audioContent=encoded_string)
                            response.audio.append(audio_output)
                            logger.info(
                                f"Generated audio for input {input_idx + 1}, size: {len(audio_bytes)} bytes"
                            )

                        except Exception as e:
                            postprocess_span.set_status(
                                Status(StatusCode.ERROR, str(e))
                            )
                            postprocess_span.record_exception(e)
                            logger.error(
                                f"Failed to process text input {input_idx + 1}: {e}"
                            )
                            # DB failure recording: single path in outer ``except`` (avoids duplicate rows).
                            raise

                    postprocess_span.set_attribute(
                        "tts.postprocess.built_audio_output_count", len(response.audio)
                    )
                    postprocess_span.add_event(
                        "tts.postprocess.completed",
                        {"audio_output_count": len(response.audio)},
                    )

                total_audio_duration = None
                total_audio_size = 0

                # Phase 6: single persist — create request, store results, update status
                with _standard_spans.persist() as persist_span:
                    persist_span.set_attribute(
                        "tts.db.operations",
                        "tts_requests.insert,tts_results.insert,tts_requests.status_update",
                    )
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
                    persist_span.set_attribute("tts.db.tts_request.id", str(request_id))
                    persist_span.set_attribute("tts.request_id", str(request_id))
                    persist_span.set_attribute("tts.db.tts_request.model_id", service_id)
                    persist_span.set_attribute("tts.db.tts_request.voice_id", gender)
                    persist_span.set_attribute("tts.db.tts_request.language", language)
                    persist_span.set_attribute(
                        "tts.db.tts_request.text_length", total_text_length
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_request.status_after_insert", "processing"
                    )
                    persist_span.add_event(
                        "tts.db.tts_request.insert",
                        {
                            "table": "tts_requests",
                            "request_id": str(request_id),
                            "model_id": service_id,
                            "voice_id": gender,
                            "language": language,
                            "text_length": total_text_length,
                            "initial_status": "processing",
                        },
                    )

                    if response.audio:
                        total_audio_size = sum(
                            len(base64.b64decode(a.audioContent))
                            for a in response.audio
                        )
                        total_samples = total_audio_size / 2
                        total_audio_duration = total_samples / target_sr

                    response.config = AudioConfig(
                        language=request.config.language,
                        audioFormat=request.config.audioFormat,
                        encoding="base64",
                        samplingRate=target_sr,
                        audioDuration=total_audio_duration,
                    )

                    last_encoded = (
                        response.audio[-1].audioContent if response.audio else ""
                    )
                    preview_len = min(100, len(last_encoded)) if last_encoded else 0
                    await self.repository.create_result(
                        request_id=request_id,
                        audio_file_path=last_encoded[:100] if last_encoded else "",
                        audio_duration=total_audio_duration,
                        audio_format=fmt,
                        sample_rate=target_sr,
                        file_size=total_audio_size,
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_result.audio_path_preview_length", preview_len
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_result.audio_duration_seconds",
                        total_audio_duration or 0.0,
                    )
                    persist_span.set_attribute("tts.db.tts_result.audio_format", fmt)
                    persist_span.set_attribute(
                        "tts.db.tts_result.sample_rate_hz", target_sr
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_result.file_size_bytes", total_audio_size
                    )
                    persist_span.add_event(
                        "tts.db.tts_result.insert",
                        {
                            "table": "tts_results",
                            "request_id": str(request_id),
                            "audio_format": fmt,
                            "sample_rate_hz": target_sr,
                            "file_size_bytes": total_audio_size,
                            "audio_duration_seconds": total_audio_duration or 0.0,
                        },
                    )

                    processing_time = time.time() - start_time
                    await self.repository.update_request_status(
                        request_id, "completed", processing_time=processing_time
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_request.final_status", "completed"
                    )
                    persist_span.set_attribute(
                        "tts.db.tts_request.processing_time_seconds",
                        processing_time,
                    )
                    persist_span.add_event(
                        "tts.db.tts_request.status_update",
                        {
                            "table": "tts_requests",
                            "request_id": str(request_id),
                            "status": "completed",
                            "processing_time_seconds": processing_time,
                        },
                    )

                total_output_audio_duration = (
                    total_audio_duration if total_audio_duration else 0.0
                )

                if parent_span is not None:
                    try:
                        parent_span.set_attribute(
                            "tts.output_count", len(response.audio)
                        )
                        parent_span.set_attribute(
                            "tts.output.audio_length_seconds",
                            total_output_audio_duration,
                        )
                        parent_span.set_attribute(
                            "tts.output.audio_length_ms",
                            total_output_audio_duration * 1000.0,
                        )
                        if total_audio_size > 0:
                            parent_span.set_attribute(
                                "tts.output.audio_size_bytes", total_audio_size
                            )
                    except Exception:
                        pass

                processing_time = time.time() - start_time
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
                logger.error(
                    f"TTS inference failed: {e}",
                    extra={
                        "context": {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "service_id": (
                                request.config.serviceId
                                if hasattr(request, "config") and request.config
                                else None
                            ),
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
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(
                            f"Failed to update request status: {update_error}"
                        )
                else:
                    try:
                        ttl = sum(len(inp.source) for inp in request.input)
                        dr = await self.repository.create_request(
                            model_id=service_id,
                            voice_id=gender,
                            language=language,
                            text_length=ttl,
                            user_id=user_id,
                            api_key_id=api_key_id,
                            session_id=session_id,
                        )
                        await self.repository.update_request_status(
                            dr.id, "failed", error_message=str(e)
                        )
                    except Exception as db_err:
                        logger.error(
                            "TTS: failed to record failed request in DB: %s",
                            db_err,
                        )

                if isinstance(e, TritonInferenceError):
                    raise
                raise TritonInferenceError(f"TTS inference failed: {e}")
