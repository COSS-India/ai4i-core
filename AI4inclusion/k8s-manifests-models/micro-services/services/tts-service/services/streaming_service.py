import asyncio
import base64
import json
import logging
import time
from typing import Dict, Optional, Any
from uuid import uuid4

# Try to import socketio, but make it optional
try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    socketio = None

from models.streaming_models import (
    StreamingTTSConfig,
    StreamingTextChunk,
    StreamingAudioResponse,
    StreamingTTSError,
    StreamingTTSSessionState
)
from services.voice_service import VoiceService, VoiceNotFoundError
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from repositories.tts_repository import TTSRepository
from utils.audio_utils import convert_audio_format

logger = logging.getLogger(__name__)


class StreamingTTSService:
    """TTS streaming service using Socket.IO for real-time text-to-speech."""
    
    def __init__(
        self,
        audio_service: AudioService,
        text_service: TextService,
        triton_client: TritonClient,
        repository: TTSRepository,
        voice_service: VoiceService,
        redis_client,
        response_frequency_in_ms: int = 2000
    ):
        """Initialize TTS streaming service."""
        if not SOCKETIO_AVAILABLE:
            raise ImportError("socketio module is required for StreamingTTSService but not available")
        self.audio_service = audio_service
        self.text_service = text_service
        self.triton_client = triton_client
        self.repository = repository
        self.voice_service = voice_service
        self.redis_client = redis_client
        self.response_frequency_in_ms = response_frequency_in_ms
        
        # Initialize Socket.IO server
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins='*'
        )
        self.app = socketio.ASGIApp(self.sio, socketio_path='')
        
        # Client session states
        self.client_states: Dict[str, StreamingTTSSessionState] = {}
        
        # Configure socket event handlers
        self.configure_socket_server()
    
    def configure_socket_server(self):
        """Configure Socket.IO event handlers."""
        
        @self.sio.event
        async def connect(sid: str, environ: dict, auth):
            """Handle client connection."""
            try:
                # Parse query parameters
                query_string = environ.get('QUERY_STRING', '')
                query_params = self._parse_query_string(query_string)
                
                # Validate required parameters
                service_id = query_params.get('serviceId')
                voice_id = query_params.get('voice_id')
                language = query_params.get('language')
                gender = query_params.get('gender')
                
                if not all([service_id, voice_id, language, gender]):
                    await self.sio.emit('error', {
                        'error': 'Missing required parameters: serviceId, voice_id, language, gender',
                        'code': 'MISSING_PARAMETERS',
                        'timestamp': time.time()
                    }, room=sid)
                    return False
                
                # Validate voice exists
                try:
                    model_id, resolved_gender = self.voice_service.resolve_voice(voice_id)
                except VoiceNotFoundError:
                    await self.sio.emit('error', {
                        'error': f'Voice not found: {voice_id}',
                        'code': 'VOICE_NOT_FOUND',
                        'timestamp': time.time()
                    }, room=sid)
                    return False
                
                # Parse optional parameters
                sampling_rate = int(query_params.get('samplingRate', 22050))
                audio_format = query_params.get('audioFormat', 'wav')
                api_key = query_params.get('apiKey')
                
                # Create streaming config
                config = StreamingTTSConfig(
                    serviceId=service_id,
                    voice_id=voice_id,
                    language=language,
                    gender=gender,
                    samplingRate=sampling_rate,
                    audioFormat=audio_format
                )
                
                # Initialize session state
                await self.initialize_session_state(
                    sid, config, api_key, None, None
                )
                
                logger.info(f"TTS streaming client connected: {sid}")
                return True
                
            except Exception as e:
                logger.error(f"Connection error for {sid}: {e}")
                await self.sio.emit('error', {
                    'error': f'Connection failed: {str(e)}',
                    'code': 'CONNECTION_FAILED',
                    'timestamp': time.time()
                }, room=sid)
                return False
        
        @self.sio.on('start')
        async def start(sid: str, config_update: Optional[Dict] = None):
            """Handle stream start."""
            try:
                if sid not in self.client_states:
                    await self.sio.emit('error', {
                        'error': 'Session not found',
                        'code': 'SESSION_NOT_FOUND',
                        'timestamp': time.time()
                    }, room=sid)
                    return
                
                state = self.client_states[sid]
                
                # Update config if provided
                if config_update:
                    if 'responseFrequencyInMs' in config_update:
                        state.config.responseFrequencyInMs = config_update['responseFrequencyInMs']
                    if 'audioFormat' in config_update:
                        state.config.audioFormat = config_update['audioFormat']
                
                # Reset text buffer
                state.reset_buffer()
                
                # Emit ready event
                await self.sio.emit('ready', room=sid)
                logger.info(f"TTS stream started: {sid}")
                
            except Exception as e:
                logger.error(f"Start error for {sid}: {e}")
                await self.sio.emit('error', {
                    'error': f'Start failed: {str(e)}',
                    'code': 'START_FAILED',
                    'timestamp': time.time()
                }, room=sid)
        
        @self.sio.on('data')
        async def data(sid: str, text: str, is_final: bool = False, disconnect_stream: bool = False):
            """Handle text data."""
            try:
                if sid not in self.client_states:
                    await self.sio.emit('error', {
                        'error': 'Session not found',
                        'code': 'SESSION_NOT_FOUND',
                        'timestamp': time.time()
                    }, room=sid)
                    return
                
                state = self.client_states[sid]
                
                # Add text to buffer
                if text:
                    state.add_text(text)
                
                # Process if final or disconnect requested
                if is_final or disconnect_stream:
                    if state.text_buffer.strip():
                        await self.synthesize_and_emit(sid, is_final)
                
                # Handle disconnect
                if disconnect_stream:
                    await self.delete_session_state(sid)
                    await self.sio.emit('terminate', room=sid)
                    logger.info(f"TTS stream terminated: {sid}")
                
            except Exception as e:
                logger.error(f"Data error for {sid}: {e}")
                await self.sio.emit('error', {
                    'error': f'Data processing failed: {str(e)}',
                    'code': 'DATA_PROCESSING_FAILED',
                    'timestamp': time.time()
                }, room=sid)
        
        @self.sio.event
        def disconnect(sid: str):
            """Handle client disconnection."""
            try:
                if sid in self.client_states:
                    asyncio.create_task(self.delete_session_state(sid))
                    logger.info(f"TTS streaming client disconnected: {sid}")
            except Exception as e:
                logger.error(f"Disconnect error for {sid}: {e}")
    
    def _parse_query_string(self, query_string: str) -> Dict[str, str]:
        """Parse query string into dictionary."""
        params = {}
        if query_string:
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
        return params
    
    async def initialize_session_state(
        self,
        sid: str,
        config: StreamingTTSConfig,
        api_key: Optional[str],
        user_id: Optional[int],
        api_key_id: Optional[int]
    ):
        """Initialize session state and create database request."""
        try:
            # Create database request record
            request_id = str(uuid4())
            
            # Create session state
            state = StreamingTTSSessionState(
                session_id=sid,
                config=config,
                api_key=api_key,
                user_id=user_id,
                api_key_id=api_key_id,
                request_id=request_id
            )
            
            # Store session state
            self.client_states[sid] = state
            
            logger.info(f"Session state initialized: {sid}")
            
        except Exception as e:
            logger.error(f"Failed to initialize session state for {sid}: {e}")
            raise
    
    async def delete_session_state(self, sid: str):
        """Delete session state and update database."""
        try:
            if sid in self.client_states:
                state = self.client_states[sid]
                
                # Update database request status if needed
                if state.request_id:
                    # Update request status to completed
                    pass  # Add database update logic here
                
                # Remove from client states
                del self.client_states[sid]
                
                logger.info(f"Session state deleted: {sid}")
                
        except Exception as e:
            logger.error(f"Failed to delete session state for {sid}: {e}")
    
    async def synthesize_and_emit(self, sid: str, is_final: bool):
        """Synthesize text and emit audio chunks."""
        try:
            state = self.client_states[sid]
            
            if not state.text_buffer.strip():
                return
            
            # Run TTS inference
            total_duration = await self.run_tts_inference(sid)
            
            # Create response
            response = StreamingAudioResponse(
                audioContent="",  # Will be set in run_tts_inference
                isFinal=is_final,
                duration=total_duration,
                timestamp=time.time(),
                format=state.config.audioFormat
            )
            
            # Emit response
            await self.sio.emit('response', data=response.dict(), room=sid)
            
            # Reset buffer
            state.reset_buffer()
            
            logger.info(f"Audio synthesized and emitted: {sid}, duration: {total_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Synthesis error for {sid}: {e}")
            await self.sio.emit('error', {
                'error': f'Synthesis failed: {str(e)}',
                'code': 'SYNTHESIS_FAILED',
                'timestamp': time.time()
            }, room=sid)
    
    async def run_tts_inference(self, sid: str) -> float:
        """Run TTS inference on buffered text."""
        state = self.client_states[sid]
        total_duration = 0.0
        
        try:
            # Get text chunks
            text_chunks = state.get_text_chunks(max_length=400)
            
            for i, chunk in enumerate(text_chunks):
                if not chunk.strip():
                    continue
                
                # Process text
                processed_text = self.text_service.process_tts_input(chunk)
                
                # Resolve voice to model and gender
                model_id, gender = self.voice_service.resolve_voice(state.config.voice_id)
                
                # Prepare Triton inputs
                inputs, outputs = self.triton_client.get_tts_io_for_triton(
                    processed_text, gender, state.config.language
                )
                
                # Send Triton request
                response = self.triton_client.send_triton_request("tts", input_list=inputs, output_list=outputs)
                
                # Extract audio
                raw_audio = response.as_numpy("OUTPUT_GENERATED_AUDIO")[0]
                
                # Resample if needed
                target_sr = state.config.samplingRate
                if target_sr != 22050:
                    raw_audio = self.audio_service.resample_audio(raw_audio, 22050, target_sr)
                
                # Convert audio format if needed
                audio_format = state.config.audioFormat
                if audio_format != "wav":
                    raw_audio = convert_audio_format(raw_audio, "wav", audio_format)
                
                # Encode to base64
                audio_base64 = base64.b64encode(raw_audio).decode('utf-8')
                
                # Calculate duration (approximate)
                duration = len(raw_audio) / target_sr
                total_duration += duration
                
                # Emit audio chunk
                chunk_response = StreamingAudioResponse(
                    audioContent=audio_base64,
                    isFinal=(i == len(text_chunks) - 1),
                    duration=duration,
                    timestamp=time.time(),
                    format=audio_format
                )
                
                await self.sio.emit('response', data=chunk_response.dict(), room=sid)
                
                # Add delay between chunks if needed
                if i < len(text_chunks) - 1:
                    await asyncio.sleep(0.1)
            
            return total_duration
            
        except Exception as e:
            logger.error(f"TTS inference error for {sid}: {e}")
            raise
