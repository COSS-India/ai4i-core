"""
Main ASR service class containing core inference logic.

Adapted from Dhruva-Platform-2 run_asr_triton_inference method.
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

from models.asr_request import ASRInferenceRequest
from models.asr_response import ASRInferenceResponse, TranscriptOutput, NBestToken
from repositories.asr_repository import ASRRepository
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from middleware.exceptions import (
    TritonInferenceError,
    ModelNotFoundError,
    ServiceUnavailableError,
    AudioProcessingError
)

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


class ASRService:
    """Main ASR service for speech-to-text conversion."""
    
    def __init__(self, repository: ASRRepository, audio_service: AudioService, triton_client: TritonClient, resolved_model_name: Optional[str] = None):
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
        session_id: Optional[int] = None
    ) -> ASRInferenceResponse:
        """Run ASR inference on audio inputs."""
        start_time = time.time()
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            language = request.config.language.sourceLanguage
            pre_processors = request.config.preProcessors or []
            post_processors = request.config.postProcessors or []
            transcription_format = request.config.transcriptionFormat
            best_token_count = request.config.bestTokenCount
            
            # Validate language code - Triton model only supports Indic languages
            from utils.validation_utils import SUPPORTED_LANGUAGES, InvalidLanguageCodeError
            if language not in SUPPORTED_LANGUAGES:
                raise InvalidLanguageCodeError(
                    f"Language '{language}' is not supported by the IndicASR model. "
                    f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}. "
                    f"Note: English ('en') is not supported by this Indic language ASR model."
                )
            
            # Use resolved model name from Model Management (REQUIRED - no fallback)
            if not self.resolved_model_name:
                raise TritonInferenceError(
                    f"Model name not resolved via Model Management for serviceId: {service_id}. "
                    f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
                )
            model_name = self.resolved_model_name
            
            standard_rate = 16000  # Target sample rate
            
            # Create database request record
            db_request = await self.repository.create_request(
                model_id=service_id,
                language=language,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            logger.info(f"Created ASR request {db_request.id} for {len(request.audio)} audio inputs")
            
            # Initialize response
            response = ASRInferenceResponse(output=[])
            
            # Process each audio input with detailed spans
            for audio_idx, audio_input in enumerate(request.audio):
                try:
                    logger.info(f"Processing audio input {audio_idx + 1}/{len(request.audio)}")
                    
                    # Create span for processing this audio input
                    if tracer:
                        audio_span_context = tracer.start_as_current_span("asr.process_audio_input")
                    else:
                        audio_span_context = nullcontext()
                    
                    with audio_span_context as audio_span:
                        if audio_span:
                            audio_span.set_attribute("asr.audio_index", audio_idx + 1)
                            audio_span.set_attribute("asr.total_audio_count", len(request.audio))
                        
                        # Get audio bytes
                        if tracer:
                            get_bytes_span_context = tracer.start_as_current_span("asr.get_audio_bytes")
                        else:
                            get_bytes_span_context = nullcontext()
                        
                        with get_bytes_span_context as get_bytes_span:
                            audio_bytes = await self._get_audio_bytes(audio_input)
                            if get_bytes_span:
                                get_bytes_span.set_attribute("asr.audio_size_bytes", len(audio_bytes))
                                get_bytes_span.set_attribute("asr.has_audio_content", bool(audio_input.audioContent))
                                get_bytes_span.set_attribute("asr.has_audio_uri", bool(audio_input.audioUri))
                        
                        # Process audio
                        if tracer:
                            process_span_context = tracer.start_as_current_span("asr.process_audio")
                        else:
                            process_span_context = nullcontext()
                        
                        with process_span_context as process_span:
                            file_handle = BytesIO(audio_bytes)
                            processed_audio = await self._process_audio_input(file_handle, standard_rate)
                            if process_span:
                                process_span.set_attribute("asr.sample_rate", standard_rate)
                                process_span.set_attribute("asr.audio_length_samples", len(processed_audio) if hasattr(processed_audio, '__len__') else 0)
                        
                        # Run preprocessors
                        if tracer:
                            preprocess_span_context = tracer.start_as_current_span("asr.preprocess")
                        else:
                            preprocess_span_context = nullcontext()
                        
                        with preprocess_span_context as preprocess_span:
                            audio_chunks, speech_timestamps = await self._run_asr_pre_processors(
                                processed_audio, pre_processors, standard_rate
                            )
                            if preprocess_span:
                                preprocess_span.set_attribute("asr.chunks_count", len(audio_chunks))
                                preprocess_span.set_attribute("asr.preprocessors_count", len(pre_processors))
                                preprocess_span.set_attribute("asr.has_timestamps", len(speech_timestamps) > 0)
                        
                        # Batch inference
                        transcript_lines = []
                        n_best_tokens = []
                        
                        batch_size = 32 if "whisper" not in service_id.lower() else 1
                        
                        if tracer:
                            batch_span_context = tracer.start_as_current_span("asr.batch_inference")
                        else:
                            batch_span_context = nullcontext()
                        
                        with batch_span_context as batch_span:
                            if batch_span:
                                batch_span.set_attribute("asr.total_chunks", len(audio_chunks))
                                batch_span.set_attribute("asr.batch_size", batch_size)
                                batch_span.set_attribute("asr.total_batches", (len(audio_chunks) + batch_size - 1) // batch_size)
                            
                            for i in range(0, len(audio_chunks), batch_size):
                                batch = audio_chunks[i:i + batch_size]
                                
                                # Prepare Triton inputs/outputs
                                if tracer:
                                    prepare_span_context = tracer.start_as_current_span("asr.prepare_triton_inputs")
                                else:
                                    prepare_span_context = nullcontext()
                                
                                with prepare_span_context as prepare_span:
                                    inputs, outputs = self.triton_client.get_asr_io_for_triton(
                                        batch, service_id, language, best_token_count
                                    )
                                    if prepare_span:
                                        prepare_span.set_attribute("asr.batch_index", i // batch_size + 1)
                                        prepare_span.set_attribute("asr.batch_chunk_count", len(batch))
                                        prepare_span.set_attribute("asr.input_count", len(inputs))
                                        prepare_span.set_attribute("asr.output_count", len(outputs))
                                
                                # Send Triton request (this will create its own triton.inference span)
                                triton_response = self.triton_client.send_triton_request(
                                    model_name, inputs, outputs
                                )
                                
                                # Extract transcripts
                                if tracer:
                                    extract_span_context = tracer.start_as_current_span("asr.extract_transcripts")
                                else:
                                    extract_span_context = nullcontext()
                                
                                with extract_span_context as extract_span:
                                    transcripts = triton_response.as_numpy("TRANSCRIPTS")
                                    if extract_span:
                                        extract_span.set_attribute("asr.transcripts_count", len(transcripts))
                                    
                                    # Decode and accumulate
                                    for j, transcript_bytes in enumerate(transcripts):
                                        transcript_text = transcript_bytes.decode('utf-8')
                                        
                                        if best_token_count > 0:
                                            # Parse JSON for n-best tokens
                                            try:
                                                transcript_data = json.loads(transcript_text)
                                                transcript_text = transcript_data.get("source", transcript_text)
                                                
                                                if "nBestTokens" in transcript_data:
                                                    n_best_tokens.extend(transcript_data["nBestTokens"])
                                            except json.JSONDecodeError:
                                                pass  # Use raw transcript text
                                        
                                        # Add timestamp if available
                                        if i + j < len(speech_timestamps):
                                            timestamp = speech_timestamps[i + j]
                                            transcript_lines.append({
                                                "text": transcript_text,
                                                "start": timestamp.get("start_secs", 0),
                                                "end": timestamp.get("end_secs", 0)
                                            })
                                        else:
                                            transcript_lines.append({
                                                "text": transcript_text,
                                                "start": 0,
                                                "end": 0
                                            })
                        
                        # Run postprocessors
                        if tracer:
                            postprocess_span_context = tracer.start_as_current_span("asr.postprocess")
                        else:
                            postprocess_span_context = nullcontext()
                        
                        with postprocess_span_context as postprocess_span:
                            processed_transcript_lines = await self._run_asr_post_processors(
                                transcript_lines, post_processors, language
                            )
                            if postprocess_span:
                                postprocess_span.set_attribute("asr.postprocessors_count", len(post_processors))
                                postprocess_span.set_attribute("asr.input_lines_count", len(transcript_lines))
                                postprocess_span.set_attribute("asr.output_lines_count", len(processed_transcript_lines))
                    
                    # Format response
                    transcript = self._create_asr_response_format(
                        processed_transcript_lines, transcription_format
                    )
                    
                    # Create n-best tokens if available
                    n_best_tokens_list = None
                    if n_best_tokens:
                        n_best_tokens_list = [
                            NBestToken(
                                word=token.get("word", ""),
                                tokens=token.get("tokens", [])
                            )
                            for token in n_best_tokens
                        ]
                    
                    # Create transcript output
                    transcript_output = TranscriptOutput(
                        source=transcript,
                        nBestTokens=n_best_tokens_list
                    )
                    
                    response.output.append(transcript_output)
                    
                    # Create database result record
                    await self.repository.create_result(
                        request_id=db_request.id,
                        transcript=transcript,
                        confidence_score=None,  # TODO: Extract from Triton response
                        word_timestamps=[line for line in processed_transcript_lines if "start" in line],
                        language_detected=language,
                        audio_format=request.config.audioFormat.value if request.config.audioFormat else None,
                        sample_rate=standard_rate
                    )
                    
                    logger.info(f"Completed processing audio input {audio_idx + 1}")
                    
                except Exception as e:
                    logger.error(f"Failed to process audio input {audio_idx + 1}: {e}")
                    # Add empty transcript for failed input
                    response.output.append(TranscriptOutput(source="", nBestTokens=None))
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                db_request.id, "completed", processing_time
            )
            
            logger.info(f"Completed ASR inference in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"ASR inference failed: {e}")
            
            # Update request status to failed
            if 'db_request' in locals():
                await self.repository.update_request_status(
                    db_request.id, "failed", error_message=str(e)
                )
            
            raise
    
    async def _get_audio_bytes(self, audio_input) -> bytes:
        """Extract audio bytes from AudioInput."""
        from utils.validation_utils import UploadFailedError, UploadTimeoutError
        
        try:
            if audio_input.audioContent:
                # Decode base64
                return base64.b64decode(audio_input.audioContent)
            elif audio_input.audioUri:
                # Download from URL
                return await self.audio_service.download_audio(str(audio_input.audioUri))
            else:
                from utils.validation_utils import NoFileSelectedError
                raise NoFileSelectedError("No audio content or URI provided")
        except (UploadFailedError, UploadTimeoutError, NoFileSelectedError):
            # Re-raise specific upload errors
            raise
        except Exception as e:
            logger.error(f"Failed to get audio bytes: {e}")
            from utils.validation_utils import UploadFailedError
            raise UploadFailedError("File upload failed. Please check your internet connection and try again.")
    
    async def _process_audio_input(self, file_handle: BytesIO, target_rate: int) -> np.ndarray:
        """Process audio input through preprocessing pipeline."""
        try:
            # Read audio file with format detection
            # Try reading with soundfile first, if it fails, try with pydub
            try:
                audio_data, sample_rate = sf.read(file_handle)
            except Exception as sf_error:
                logger.warning(f"soundfile failed to read audio: {sf_error}, trying pydub")
                # Reset file handle position
                file_handle.seek(0)
                # Try with pydub
                from pydub import AudioSegment
                audio_segment = AudioSegment.from_file(file_handle)
                sample_rate = audio_segment.frame_rate
                # Convert to numpy array
                audio_data = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
                # Normalize to [-1, 1] range
                audio_data = audio_data / (2**15)  # Assuming 16-bit audio
                # Handle stereo
                if audio_segment.channels == 2:
                    audio_data = audio_data.reshape((-1, 2))
            
            # Convert to mono
            audio_mono = self.audio_service.stereo_to_mono(audio_data)
            
            # Resample to target rate
            audio_resampled = self.audio_service.resample_audio(
                audio_mono, sample_rate, target_rate
            )
            
            # Equalize amplitude
            audio_segment = self.audio_service.equalize_amplitude(
                audio_resampled, target_rate
            )
            
            # Dequantize back to float
            final_audio = self.audio_service.dequantize_audio(audio_segment)
            
            return final_audio
            
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            raise AudioProcessingError(f"Audio processing failed: {e}")
    
    async def _run_asr_pre_processors(
        self,
        audio: np.ndarray,
        pre_processors: List[str],
        sample_rate: int
    ) -> Tuple[List[np.ndarray], List[Dict[str, float]]]:
        """Run audio preprocessing."""
        if "vad" in pre_processors:
            # Run VAD chunking
            return await self.audio_service.silero_vad_chunking(
                audio, sample_rate, triton_client=self.triton_client
            )
        else:
            # Return single chunk
            return [audio], [{"start": 0, "end": len(audio), "start_secs": 0, "end_secs": len(audio) / sample_rate}]
    
    async def _run_asr_post_processors(
        self,
        transcript_lines: List[Dict[str, Any]],
        post_processors: List[str],
        language: str
    ) -> List[Dict[str, Any]]:
        """Run text postprocessing."""
        # TODO: Implement ITN and punctuation postprocessors
        # For now, return as-is
        return transcript_lines
    
    def _create_asr_response_format(
        self,
        transcript_lines: List[Dict[str, Any]],
        transcription_format: str
    ) -> str:
        """Format transcript based on requested format."""
        if transcription_format == "srt":
            return self._format_as_srt(transcript_lines)
        elif transcription_format == "webvtt":
            return self._format_as_webvtt(transcript_lines)
        else:  # transcript
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
            srt_content.append("")  # Empty line between subtitles
        
        return "\n".join(srt_content)
    
    def _format_as_webvtt(self, transcript_lines: List[Dict[str, Any]]) -> str:
        """Format transcript as WebVTT subtitles."""
        webvtt_content = ["WEBVTT", ""]
        
        for line in transcript_lines:
            start_time = self._format_webvtt_timestamp(line.get("start", 0))
            end_time = self._format_webvtt_timestamp(line.get("end", 0))
            
            webvtt_content.append(f"{start_time} --> {end_time}")
            webvtt_content.append(line["text"])
            webvtt_content.append("")  # Empty line between subtitles
        
        return "\n".join(webvtt_content)
    
    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _format_webvtt_timestamp(self, seconds: float) -> str:
        """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"
