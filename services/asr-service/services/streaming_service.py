"""
Streaming ASR service using Socket.IO for real-time audio processing.

This module implements WebSocket-based streaming ASR functionality, allowing
clients to send audio chunks in real-time and receive partial and final
transcripts with low latency.
"""

import asyncio
import io
import json
import logging
import time
import urllib.parse
import wave
from typing import Dict, Optional, Any
import numpy as np
import soundfile as sf
import socketio

from models.streaming_models import (
    StreamingConfig,
    StreamingAudioChunk,
    StreamingResponse,
    StreamingSessionState,
    StreamingError
)
from services.audio_service import AudioService
from utils.triton_client import TritonClient
from repositories.asr_repository import ASRRepository, get_db_session
from middleware.auth_provider import validate_api_key, hash_api_key
from middleware.exceptions import AuthenticationError, InvalidAPIKeyError

logger = logging.getLogger(__name__)


class StreamingASRService:
    """Socket.IO based streaming ASR service."""
    
    def __init__(
        self,
        audio_service: AudioService,
        triton_client: TritonClient,
        repository: ASRRepository,
        redis_client,
        response_frequency_in_ms: int = 2000,
        bytes_per_sample: int = 2
    ):
        """Initialize streaming ASR service.
        
        Args:
            audio_service: Audio processing service
            triton_client: Triton inference client
            repository: ASR database repository
            redis_client: Redis client for caching
            response_frequency_in_ms: How often to emit partial transcripts
            bytes_per_sample: Bytes per audio sample (2 for int16)
        """
        self.audio_service = audio_service
        self.triton_client = triton_client
        self.repository = repository
        self.redis_client = redis_client
        self.response_frequency_in_ms = response_frequency_in_ms
        self.bytes_per_sample = bytes_per_sample
        
        # Initialize Socket.IO server
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins='*',
            logger=True,
            engineio_logger=True
        )
        self.app = socketio.ASGIApp(self.sio, socketio_path='/socket.io')
        
        # Client session states
        self.client_states: Dict[str, StreamingSessionState] = {}
        
        # Configure event handlers
        self.configure_socket_server()
    
    def configure_socket_server(self) -> None:
        """Configure Socket.IO event handlers."""
        
        @self.sio.event
        async def connect(sid: str, environ: dict, auth):
            """Handle client connection."""
            try:
                # Parse query parameters
                query_string = environ.get('QUERY_STRING', '')
                query_params = urllib.parse.parse_qs(query_string)
                
                # Extract required parameters
                service_id = query_params.get('serviceId', [None])[0]
                language = query_params.get('language', [None])[0]
                sampling_rate = query_params.get('samplingRate', ['16000'])[0]
                api_key = query_params.get('apiKey', [None])[0]
                
                # Extract optional parameters
                preprocessors = query_params.get('preProcessors', [None])[0]
                postprocessors = query_params.get('postProcessors', [None])[0]
                
                # Validate required fields
                if not service_id or not language:
                    error = StreamingError(
                        error="Missing required parameters: serviceId and language are required",
                        code="MISSING_PARAMETERS"
                    )
                    await self.sio.emit('error', data=error.dict(), room=sid)
                    return False
                
                # Parse optional parameters
                preprocessors_list = None
                postprocessors_list = None
                
                if preprocessors:
                    try:
                        preprocessors_list = json.loads(preprocessors)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid preProcessors JSON for session {sid}")
                
                if postprocessors:
                    try:
                        postprocessors_list = json.loads(postprocessors)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid postProcessors JSON for session {sid}")
                
                # Check authentication settings
                import os
                auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
                require_api_key = os.getenv("REQUIRE_API_KEY", "true").lower() == "true"
                allow_anonymous = os.getenv("ALLOW_ANONYMOUS_ACCESS", "false").lower() == "true"
                
                # Validate API key if authentication is enabled and API key is provided
                user_id = None
                api_key_id = None
                if auth_enabled and require_api_key and api_key:
                    try:
                        async with get_db_session() as session:
                            api_key_db, user_db = await validate_api_key(api_key, session, self.redis_client)
                            user_id = user_db.id
                            api_key_id = api_key_db.id
                    except Exception as e:
                        logger.error(f"Authentication failed for streaming connection: {e}")
                        await self.sio.emit('error', {'error': 'Authentication failed', 'code': 'AUTH_ERROR'}, room=sid)
                        return False
                elif auth_enabled and require_api_key and not api_key and not allow_anonymous:
                    logger.error("API key required but not provided for streaming connection")
                    await self.sio.emit('error', {'error': 'API key required', 'code': 'AUTH_ERROR'}, room=sid)
                    return False
                
                # Create streaming configuration
                config = StreamingConfig(
                    serviceId=service_id,
                    language=language,
                    samplingRate=int(sampling_rate),
                    preProcessors=preprocessors_list,
                    postProcessors=postprocessors_list,
                    enableVAD='vad' in (preprocessors_list or [])
                )
                
                # Initialize session state
                await self.initialize_session_state(sid, config, api_key, user_id, api_key_id)
                
                logger.info(f"Client connected: {sid} with config: {config.serviceId}, {config.language}")
                return True
                
            except Exception as e:
                logger.error(f"Connection error for session {sid}: {e}")
                error = StreamingError(
                    error=f"Connection failed: {str(e)}",
                    code="CONNECTION_ERROR"
                )
                await self.sio.emit('error', data=error.dict(), room=sid)
                return False
        
        @self.sio.on('start')
        async def start(sid: str, config_update: Optional[Dict] = None):
            """Handle stream start event."""
            try:
                if sid not in self.client_states:
                    await self.sio.emit('error', data={
                        'error': 'Session not found',
                        'code': 'SESSION_NOT_FOUND',
                        'timestamp': time.time()
                    }, room=sid)
                    return
                
                # Update config if provided
                if config_update:
                    state = self.client_states[sid]
                    if 'responseFrequencyInMs' in config_update:
                        state.config.responseFrequencyInMs = config_update['responseFrequencyInMs']
                        # Recalculate inference frequency
                        state.run_inference_once_in_bytes = int(
                            state.config.samplingRate * 
                            (state.config.responseFrequencyInMs / 1000) * 
                            self.bytes_per_sample
                        )
                
                # Reset buffer for new stream
                self.reset_buffer(sid)
                
                # Emit ready event
                await self.sio.emit('ready', room=sid)
                logger.info(f"Stream started for session: {sid}")
                
            except Exception as e:
                logger.error(f"Start error for session {sid}: {e}")
                await self.sio.emit('error', data={
                    'error': f'Start failed: {str(e)}',
                    'code': 'START_ERROR',
                    'timestamp': time.time()
                }, room=sid)
        
        @self.sio.on('data')
        async def data(sid: str, audio_data: bytes, is_speaking: bool, disconnect_stream: bool):
            """Handle audio data event."""
            try:
                if sid not in self.client_states:
                    await self.sio.emit('error', data={
                        'error': 'Session not found',
                        'code': 'SESSION_NOT_FOUND',
                        'timestamp': time.time()
                    }, room=sid)
                    return
                
                state = self.client_states[sid]
                
                # Add audio to buffer
                state.buffer += audio_data
                
                # Check if user stopped speaking (silence detected)
                if not is_speaking and len(state.buffer) > 0:
                    # Run final inference for current segment
                    transcript = await self.transcribe_and_emit(sid, is_final=True)
                    if transcript:
                        state.add_to_history(transcript)
                    self.reset_buffer(sid)
                
                # Check if we should run inference based on accumulated audio
                elif is_speaking and state.should_run_inference():
                    await self.transcribe_and_emit(sid, is_final=False)
                    state.update_inference_position()
                
                # Handle stream disconnection
                if disconnect_stream:
                    # Run final inference if there's remaining audio
                    if len(state.buffer) > 0:
                        transcript = await self.transcribe_and_emit(sid, is_final=True)
                        if transcript:
                            state.add_to_history(transcript)
                    
                    # Update database request status
                    if state.request_id:
                        await self.repository.update_request_status(
                            state.request_id, 
                            "completed"
                        )
                    
                    # Clean up session
                    self.delete_session_state(sid)
                    
                    # Emit terminate event
                    await self.sio.emit('terminate', room=sid)
                    logger.info(f"Stream terminated for session: {sid}")
                
            except Exception as e:
                logger.error(f"Data processing error for session {sid}: {e}")
                await self.sio.emit('error', data={
                    'error': f'Data processing failed: {str(e)}',
                    'code': 'DATA_PROCESSING_ERROR',
                    'timestamp': time.time()
                }, room=sid)
        
        @self.sio.event
        def disconnect(sid: str):
            """Handle client disconnection."""
            try:
                self.delete_session_state(sid)
                logger.info(f"Client disconnected: {sid}")
            except Exception as e:
                logger.error(f"Disconnect error for session {sid}: {e}")
    
    async def initialize_session_state(
        self, 
        sid: str, 
        config: StreamingConfig, 
        api_key: Optional[str] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None
    ) -> None:
        """Initialize session state for a new connection."""
        try:
            # Calculate inference frequency based on response frequency
            run_inference_once_in_bytes = int(
                config.samplingRate * 
                (config.responseFrequencyInMs / 1000) * 
                self.bytes_per_sample
            )
            
            # Create database request record
            request_id = None
            if self.repository:
                request_id = await self.repository.create_request(
                    model_id=config.serviceId,
                    language=config.language,
                    status="streaming",
                    user_id=user_id,
                    api_key_id=api_key_id
                )
            
            # Create session state
            state = StreamingSessionState(
                session_id=sid,
                config=config,
                api_key=api_key,
                user_id=user_id,
                api_key_id=api_key_id,
                run_inference_once_in_bytes=run_inference_once_in_bytes,
                request_id=request_id
            )
            
            self.client_states[sid] = state
            logger.info(f"Session state initialized for {sid}")
            
        except Exception as e:
            logger.error(f"Failed to initialize session state for {sid}: {e}")
            raise
    
    def delete_session_state(self, sid: str) -> None:
        """Delete session state and cleanup resources."""
        try:
            if sid in self.client_states:
                state = self.client_states[sid]
                
                # Update database request status if needed
                if state.request_id and self.repository:
                    asyncio.create_task(
                        self.repository.update_request_status(
                            state.request_id, 
                            "disconnected"
                        )
                    )
                
                # Remove from client states
                del self.client_states[sid]
                logger.info(f"Session state deleted for {sid}")
                
        except Exception as e:
            logger.error(f"Failed to delete session state for {sid}: {e}")
    
    def reset_buffer(self, sid: str) -> None:
        """Reset audio buffer for a session."""
        if sid in self.client_states:
            self.client_states[sid].reset_buffer()
    
    def process_audio_chunk(self, sid: str, audio_bytes: bytes) -> np.ndarray:
        """Process audio chunk for inference."""
        try:
            state = self.client_states[sid]
            config = state.config
            
            # Convert bytes to numpy array (int16 PCM)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            
            # Convert stereo to mono if needed
            if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
                audio_array = self.audio_service.stereo_to_mono(audio_array)
            
            # Resample if needed
            if config.samplingRate != 16000:
                audio_array = self.audio_service.resample_audio(
                    audio_array, 
                    config.samplingRate, 
                    16000
                )
            
            return audio_array
            
        except Exception as e:
            logger.error(f"Audio processing error for session {sid}: {e}")
            raise
    
    async def run_inference_from_buffer(self, sid: str) -> str:
        """Run ASR inference on accumulated audio buffer."""
        try:
            state = self.client_states[sid]
            config = state.config
            
            if len(state.buffer) == 0:
                return ""
            
            # Convert buffer to WAV format
            wav_buffer = io.BytesIO()
            
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 2 bytes per sample (int16)
                wav_file.setframerate(config.samplingRate)
                wav_file.writeframes(state.buffer)
            
            wav_buffer.seek(0)
            
            # Read audio data
            audio_data, sample_rate = sf.read(wav_buffer, dtype='float32')
            
            # Process audio
            audio_array = self.process_audio_chunk(sid, state.buffer)
            
            # Prepare Triton inputs
            inputs, outputs = self.triton_client.get_asr_io_for_triton(
                [audio_array], 
                config.serviceId, 
                config.language
            )
            
            # Send Triton request
            model_name = "asr_am_ensemble"  # Default model name
            response = self.triton_client.send_triton_request(
                model_name, 
                inputs, 
                outputs
            )
            
            # Extract transcript
            transcript = response.as_numpy('TRANSCRIPTS')[0].decode('utf-8')
            
            return transcript.strip()
            
        except Exception as e:
            logger.error(f"Inference error for session {sid}: {e}")
            raise
    
    async def transcribe_and_emit(self, sid: str, is_final: bool = False) -> Optional[str]:
        """Run transcription and emit response to client."""
        try:
            if sid not in self.client_states:
                return None
            
            state = self.client_states[sid]
            
            if len(state.buffer) == 0:
                return None
            
            # Run inference
            transcript = await self.run_inference_from_buffer(sid)
            
            if not transcript:
                return None
            
            # Add to historical text if final
            if is_final:
                state.add_to_history(transcript)
            
            # Create response
            response = StreamingResponse(
                transcript=transcript,
                isFinal=is_final,
                language=state.config.language,
                timestamp=time.time()
            )
            
            # Emit to client
            await self.sio.emit('response', data=response.dict(), room=sid)
            
            logger.debug(f"Emitted transcript for {sid}: {transcript[:50]}... (final={is_final})")
            return transcript
            
        except Exception as e:
            logger.error(f"Transcription error for session {sid}: {e}")
            
            # Emit error to client
            error = StreamingError(
                error=f"Transcription failed: {str(e)}",
                code="INFERENCE_FAILED"
            )
            await self.sio.emit('error', data=error.dict(), room=sid)
            return None
