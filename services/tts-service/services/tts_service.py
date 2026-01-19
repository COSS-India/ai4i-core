"""
Main TTS service class containing core inference logic.

Adapted from Dhruva-Platform-2 run_tts_triton_inference method (lines 468-592).
"""

import asyncio
import base64
import logging
import time
from io import BytesIO
from typing import Optional, List
import numpy as np
from scipy.io import wavfile
from pydub import AudioSegment
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse, AudioOutput, AudioConfig
from repositories.tts_repository import TTSRepository
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from middleware.exceptions import (
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError
)

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("tts-service")


class TTSService:
    """Main TTS service for text-to-speech inference."""
    
    def __init__(
        self,
        repository: TTSRepository,
        audio_service: AudioService,
        text_service: TextService,
        triton_client: TritonClient
    ):
        """Initialize TTS service with dependencies."""
        self.repository = repository
        self.audio_service = audio_service
        self.text_service = text_service
        self.triton_client = triton_client
    
    async def run_inference(
        self,
        request: TTSInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> TTSInferenceResponse:
        """
        Run TTS inference for the given request.
        
        Adapted from Dhruva-Platform-2 run_tts_triton_inference method.
        """
        if not tracer:
            # Fallback if tracing not available
            return await self._run_inference_impl(request, user_id, api_key_id, session_id)
        
        start_time = time.time()
        request_id = None
        
        with tracer.start_as_current_span("tts.process_batch") as span:
            try:
                # Extract configuration
                service_id = request.config.serviceId
                language = request.config.language.sourceLanguage
                gender = request.config.gender.value
                standard_rate = 22050  # TTS standard sample rate
                target_sr = request.config.samplingRate or 22050
                audio_format = request.config.audioFormat.value
                
                # Convert PCM format to s16le for Triton
                if audio_format == "pcm":
                    format = "s16le"
                else:
                    format = audio_format
                
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
                total_text_length = sum(len(input.source) for input in request.input)
                with tracer.start_as_current_span("tts.create_db_request") as db_span:
                    db_request = await self.repository.create_request(
                        model_id=service_id,
                        voice_id=gender,
                        language=language,
                        text_length=total_text_length,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id
                    )
                    request_id = db_request.id
                    db_span.set_attribute("tts.request_id", str(request_id))
            
                # Process each text input
                for input_idx, text_input in enumerate(request.input):
                    with tracer.start_as_current_span("tts.process_input") as input_span:
                        try:
                            input_span.set_attribute("tts.input_index", input_idx)
                            input_span.set_attribute("tts.input_text_length", len(text_input.source))
                            
                            logger.info(f"Processing text input {input_idx + 1}/{len(request.input)}")
                            
                            # Process text input
                            with tracer.start_as_current_span("tts.preprocess_text") as preprocess_span:
                                processed_text = self.text_service.process_tts_input(text_input.source)
                                preprocess_span.set_attribute("tts.processed_text_length", len(processed_text))
                            
                            # Chunk long text
                            with tracer.start_as_current_span("tts.chunk_text") as chunk_span:
                                if len(processed_text) > 400:
                                    text_chunks = self.text_service.chunk_text(processed_text, max_length=400)
                                else:
                                    text_chunks = [processed_text]
                                chunk_span.set_attribute("tts.chunk_count", len(text_chunks))
                            
                            # Generate audio for each chunk
                            raw_audios = []
                            for chunk_idx, chunk in enumerate(text_chunks):
                                with tracer.start_as_current_span("tts.generate_audio_chunk") as chunk_gen_span:
                                    try:
                                        chunk_gen_span.set_attribute("tts.chunk_index", chunk_idx)
                                        chunk_gen_span.set_attribute("tts.chunk_length", len(chunk))
                                        
                                        # Prepare Triton inputs
                                        with tracer.start_as_current_span("tts.prepare_triton_inputs") as prep_span:
                                            inputs, outputs = self.triton_client.get_tts_io_for_triton(
                                                text=chunk,
                                                gender=gender,
                                                language=language
                                            )
                                            prep_span.set_attribute("tts.input_count", len(inputs))
                                        
                                        # Send Triton request (triton_client will create its own span)
                                        triton_response = self.triton_client.send_triton_request(
                                            model_name="tts",
                                            input_list=inputs,
                                            output_list=outputs
                                        )
                                        
                                        # Extract audio
                                        with tracer.start_as_current_span("tts.extract_audio") as extract_span:
                                            raw_audio = triton_response.as_numpy("OUTPUT_GENERATED_AUDIO")[0]
                                            raw_audios.append(raw_audio)
                                            extract_span.set_attribute("tts.audio_length", len(raw_audio))
                                        
                                    except Exception as e:
                                        chunk_gen_span.set_attribute("error", True)
                                        chunk_gen_span.set_attribute("error.type", type(e).__name__)
                                        chunk_gen_span.set_attribute("error.message", str(e))
                                        chunk_gen_span.set_status(Status(StatusCode.ERROR, str(e)))
                                        chunk_gen_span.record_exception(e)
                                        logger.error(f"Triton inference failed for chunk: {e}")
                                        raise TritonInferenceError(f"Triton inference failed: {e}")
                            
                            # Concatenate audio chunks
                            with tracer.start_as_current_span("tts.concatenate_audio") as concat_span:
                                if len(raw_audios) > 1:
                                    raw_audio = np.concatenate(raw_audios)
                                else:
                                    raw_audio = raw_audios[0]
                                concat_span.set_attribute("tts.final_audio_length", len(raw_audio))
                            
                            # Resample audio
                            with tracer.start_as_current_span("tts.resample_audio") as resample_span:
                                final_audio = self.audio_service.resample_audio(raw_audio, standard_rate, target_sr)
                                resample_span.set_attribute("tts.resampled_length", len(final_audio))
                                resample_span.set_attribute("tts.source_rate", standard_rate)
                                resample_span.set_attribute("tts.target_rate", target_sr)
                            
                            # Adjust duration if specified
                            if text_input.audioDuration:
                                with tracer.start_as_current_span("tts.adjust_duration") as duration_span:
                                    cur_duration = len(final_audio) / target_sr
                                    speed_factor = cur_duration / text_input.audioDuration
                                    duration_span.set_attribute("tts.current_duration", cur_duration)
                                    duration_span.set_attribute("tts.target_duration", text_input.audioDuration)
                                    duration_span.set_attribute("tts.speed_factor", speed_factor)
                                    
                                    if speed_factor > 1:  # Too long - speed up
                                        final_audio = self.audio_service.stretch_audio(
                                            final_audio, speed_factor, target_sr
                                        )
                                    elif speed_factor < 1:  # Too short - add silence
                                        silence_duration = text_input.audioDuration - cur_duration
                                        final_audio = self.audio_service.append_silence(
                                            final_audio, silence_duration, target_sr
                                        )
                            
                            # Convert to WAV format
                            with tracer.start_as_current_span("tts.convert_audio") as convert_span:
                                byte_io = BytesIO()
                                wavfile.write(byte_io, target_sr, final_audio)
                                byte_io.seek(0)
                                
                                # Convert to target format if not WAV
                                if format != "wav":
                                    audio_segment = AudioSegment.from_file(byte_io, format="wav")
                                    byte_io = BytesIO()
                                    audio_segment.export(byte_io, format=format)
                                    byte_io.seek(0)
                                
                                convert_span.set_attribute("tts.output_format", format)
                            
                            # Encode to base64
                            with tracer.start_as_current_span("tts.encode_audio") as encode_span:
                                audio_bytes = byte_io.read()
                                encoded_bytes = base64.b64encode(audio_bytes)
                                encoded_string = encoded_bytes.decode('utf-8')
                                encode_span.set_attribute("tts.audio_size_bytes", len(audio_bytes))
                                encode_span.set_attribute("tts.encoded_size_bytes", len(encoded_string))
                            
                            # Create audio output
                            audio_output = AudioOutput(audioContent=encoded_string)
                            response.audio.append(audio_output)
                            
                            input_span.set_attribute("tts.output_audio_size", len(audio_bytes))
                            logger.info(f"Generated audio for input {input_idx + 1}, size: {len(audio_bytes)} bytes")
                            
                        except Exception as e:
                            input_span.set_attribute("error", True)
                            input_span.set_attribute("error.type", type(e).__name__)
                            input_span.set_attribute("error.message", str(e))
                            input_span.set_status(Status(StatusCode.ERROR, str(e)))
                            input_span.record_exception(e)
                            logger.error(f"Failed to process text input {input_idx + 1}: {e}")
                            # Update request status to failed
                            await self.repository.update_request_status(
                                request_id, "failed", error_message=str(e)
                            )
                            raise
            
                # Create response config
                # Calculate total audio duration from all outputs
                total_audio_duration = None
                total_audio_size = 0
                last_encoded_string = ""
                
                if response.audio:
                    # Estimate duration based on audio size and sample rate
                    # This is approximate since we don't store individual durations
                    total_audio_size = sum(len(base64.b64decode(audio.audioContent)) for audio in response.audio)
                    # Approximate: assume 2 bytes per sample for 16-bit audio
                    total_samples = total_audio_size / 2
                    total_audio_duration = total_samples / target_sr
                    last_encoded_string = response.audio[-1].audioContent if response.audio else ""
                
                with tracer.start_as_current_span("tts.create_response_config") as config_span:
                    response.config = AudioConfig(
                        language=request.config.language,
                        audioFormat=request.config.audioFormat,
                        encoding="base64",
                        samplingRate=target_sr,
                        audioDuration=total_audio_duration
                    )
                    config_span.set_attribute("tts.config_created", True)
                    if total_audio_duration:
                        config_span.set_attribute("tts.total_duration", total_audio_duration)
                
                # Create database result record
                with tracer.start_as_current_span("tts.create_db_results") as results_span:
                    await self.repository.create_result(
                        request_id=request_id,
                        audio_file_path=last_encoded_string[:100] if last_encoded_string else "",
                        audio_duration=total_audio_duration,
                        audio_format=format,
                        sample_rate=target_sr,
                        file_size=total_audio_size
                    )
                    results_span.set_attribute("tts.db_results_created", len(response.audio))
                
                # Update request status
                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    request_id, "completed", processing_time=processing_time
                )
                
                span.set_attribute("tts.processing_time_seconds", processing_time)
                span.set_attribute("tts.output_count", len(response.audio))
                
                logger.info(f"TTS inference completed for request {request_id} in {processing_time:.2f}s")
                return response
                
            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.type", type(e).__name__)
                span.set_attribute("error.message", str(e))
                span.set_attribute("http.status_code", 500)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                
                # Log error with full context
                logger.error(
                    f"TTS inference failed: {e}",
                    extra={
                        "context": {
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "service_id": request.config.serviceId if hasattr(request, 'config') and request.config else None,
                            "request_id": request_id,
                            "user_id": user_id,
                            "api_key_id": api_key_id,
                            "session_id": session_id,
                        }
                    },
                    exc_info=True
                )
                
                # Update request status to failed
                if request_id:
                    try:
                        await self.repository.update_request_status(
                            request_id, "failed", error_message=str(e)
                        )
                    except Exception as update_error:
                        logger.error(f"Failed to update request status: {update_error}")
                
                # Re-raise with appropriate error type
                if isinstance(e, TritonInferenceError):
                    raise
                elif isinstance(e, AudioProcessingError):
                    raise
                else:
                    raise AudioProcessingError(f"TTS inference failed: {e}")
    
    async def _run_inference_impl(
        self,
        request: TTSInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
    ) -> TTSInferenceResponse:
        """Fallback implementation when tracing is not available."""
        start_time = time.time()
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            language = request.config.language.sourceLanguage
            gender = request.config.gender.value
            standard_rate = 22050  # TTS standard sample rate
            target_sr = request.config.samplingRate or 22050
            audio_format = request.config.audioFormat.value
            
            # Convert PCM format to s16le for Triton
            if audio_format == "pcm":
                format = "s16le"
            else:
                format = audio_format
            
            logger.info(f"Starting TTS inference for {len(request.input)} text inputs")
            
            # Initialize response
            response = TTSInferenceResponse(audio=[])
            
            # Create database request record
            total_text_length = sum(len(input.source) for input in request.input)
            db_request = await self.repository.create_request(
                model_id=service_id,
                voice_id=gender,
                language=language,
                text_length=total_text_length,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            request_id = db_request.id
            
            # Process each text input
            for input_idx, text_input in enumerate(request.input):
                try:
                    logger.info(f"Processing text input {input_idx + 1}/{len(request.input)}")
                    
                    # Process text input
                    processed_text = self.text_service.process_tts_input(text_input.source)
                    
                    # Chunk long text
                    if len(processed_text) > 400:
                        text_chunks = self.text_service.chunk_text(processed_text, max_length=400)
                    else:
                        text_chunks = [processed_text]
                    
                    # Generate audio for each chunk
                    raw_audios = []
                    for chunk in text_chunks:
                        try:
                            # Prepare Triton inputs
                            inputs, outputs = self.triton_client.get_tts_io_for_triton(
                                text=chunk,
                                gender=gender,
                                language=language
                            )
                            
                            # Send Triton request
                            triton_response = self.triton_client.send_triton_request(
                                model_name="tts",
                                input_list=inputs,
                                output_list=outputs
                            )
                            
                            # Extract audio
                            raw_audio = triton_response.as_numpy("OUTPUT_GENERATED_AUDIO")[0]
                            raw_audios.append(raw_audio)
                            
                        except Exception as e:
                            logger.error(f"Triton inference failed for chunk: {e}")
                            raise TritonInferenceError(f"Triton inference failed: {e}")
                    
                    # Concatenate audio chunks
                    if len(raw_audios) > 1:
                        raw_audio = np.concatenate(raw_audios)
                    else:
                        raw_audio = raw_audios[0]
                    
                    # Resample audio
                    final_audio = self.audio_service.resample_audio(raw_audio, standard_rate, target_sr)
                    
                    # Adjust duration if specified
                    if text_input.audioDuration:
                        cur_duration = len(final_audio) / target_sr
                        speed_factor = cur_duration / text_input.audioDuration
                        
                        if speed_factor > 1:  # Too long - speed up
                            final_audio = self.audio_service.stretch_audio(
                                final_audio, speed_factor, target_sr
                            )
                        elif speed_factor < 1:  # Too short - add silence
                            silence_duration = text_input.audioDuration - cur_duration
                            final_audio = self.audio_service.append_silence(
                                final_audio, silence_duration, target_sr
                            )
                    
                    # Convert to WAV format
                    byte_io = BytesIO()
                    wavfile.write(byte_io, target_sr, final_audio)
                    byte_io.seek(0)
                    
                    # Convert to target format if not WAV
                    if format != "wav":
                        audio_segment = AudioSegment.from_file(byte_io, format="wav")
                        byte_io = BytesIO()
                        audio_segment.export(byte_io, format=format)
                        byte_io.seek(0)
                    
                    # Encode to base64
                    audio_bytes = byte_io.read()
                    encoded_bytes = base64.b64encode(audio_bytes)
                    encoded_string = encoded_bytes.decode('utf-8')
                    
                    # Create audio output
                    audio_output = AudioOutput(audioContent=encoded_string)
                    response.audio.append(audio_output)
                    
                    # Log audio generation success
                    logger.info(f"Generated audio for input {input_idx + 1}, size: {len(audio_bytes)} bytes")
                    
                except Exception as e:
                    logger.error(f"Failed to process text input {input_idx + 1}: {e}")
                    # Update request status to failed
                    await self.repository.update_request_status(
                        request_id, "failed", error_message=str(e)
                    )
                    raise
            
            # Create response config
            response.config = AudioConfig(
                language=request.config.language,
                audioFormat=request.config.audioFormat,
                encoding="base64",
                samplingRate=target_sr,
                audioDuration=len(final_audio) / target_sr if 'final_audio' in locals() else None
            )
            
            # Create database result record
            await self.repository.create_result(
                request_id=request_id,
                audio_file_path=encoded_string[:100] if 'encoded_string' in locals() else "",
                audio_duration=len(final_audio) / target_sr if 'final_audio' in locals() else None,
                audio_format=format,
                sample_rate=target_sr,
                file_size=len(encoded_string) if 'encoded_string' in locals() else 0
            )
            
            # Update request status to completed
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                request_id, "completed", processing_time=processing_time
            )
            
            logger.info(f"TTS inference completed for request {request_id} in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"TTS inference failed: {e}")
            
            # Update request status to failed
            if 'request_id' in locals():
                await self.repository.update_request_status(
                    request_id, "failed", error_message=str(e)
                )
            
            raise
