"""
Main ASR service class containing core inference logic.

Adapted from Dhruva-Platform-2 run_asr_triton_inference method.
"""

import asyncio
import base64
import json
import logging
import time
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import soundfile as sf

from models.asr_request import ASRInferenceRequest
from models.asr_response import ASRInferenceResponse, TranscriptOutput, NBestToken
from repositories.asr_repository import ASRRepository
from services.audio_service import AudioService
from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""
    pass


class AudioProcessingError(Exception):
    """Custom exception for audio processing errors."""
    pass


class ASRService:
    """Main ASR service for speech-to-text conversion."""
    
    def __init__(self, repository: ASRRepository, audio_service: AudioService, triton_client: TritonClient):
        """Initialize ASR service with dependencies."""
        self.repository = repository
        self.audio_service = audio_service
        self.triton_client = triton_client
    
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
            
            # Use serviceId as model name for Triton
            model_name = service_id
            
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
            
            # Process each audio input
            for audio_idx, audio_input in enumerate(request.audio):
                try:
                    logger.info(f"Processing audio input {audio_idx + 1}/{len(request.audio)}")
                    
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
                        batch = audio_chunks[i:i + batch_size]
                        
                        # Prepare Triton inputs/outputs
                        inputs, outputs = self.triton_client.get_asr_io_for_triton(
                            batch, service_id, language, best_token_count
                        )
                        
                        # Send Triton request
                        triton_response = self.triton_client.send_triton_request(
                            model_name, inputs, outputs
                        )
                        
                        # Extract transcripts
                        transcripts = triton_response.as_numpy("TRANSCRIPTS")
                        
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
                    processed_transcript_lines = await self._run_asr_post_processors(
                        transcript_lines, post_processors, language
                    )
                    
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
        try:
            if audio_input.audioContent:
                # Decode base64
                return base64.b64decode(audio_input.audioContent)
            elif audio_input.audioUri:
                # Download from URL
                return await self.audio_service.download_audio(str(audio_input.audioUri))
            else:
                raise AudioProcessingError("No audio content or URI provided")
        except Exception as e:
            logger.error(f"Failed to get audio bytes: {e}")
            raise AudioProcessingError(f"Failed to get audio bytes: {e}")
    
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
