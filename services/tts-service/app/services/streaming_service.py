"""TTS streaming service using Socket.IO for real-time text-to-speech."""

import asyncio
import base64
import json
import logging
import time
from typing import Dict, Optional, Any
from uuid import uuid4

try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    socketio = None

from app.schemas.voice import VoiceMetadata, VoiceGender, VoiceAge
from app.services.voice_service import VoiceService, VoiceNotFoundError
from app.services.audio_service import AudioService
from app.services.text_service import TextService
from app.clients.triton_client import TTSTritonClient
from app.repositories.tts_repository import TTSRepository

logger = logging.getLogger(__name__)


# ── Streaming-specific models (kept local to avoid circular imports) ──

from dataclasses import dataclass
from typing import List
from pydantic import BaseModel, validator


class StreamingTTSConfig(BaseModel):
    """TTS streaming configuration."""
    serviceId: str
    voice_id: str
    language: str
    gender: str
    samplingRate: int = 22050
    audioFormat: str = "wav"
    responseFrequencyInMs: int = 2000
    encoding: str = "base64"
    enableChunking: bool = True

    @validator("language")
    def validate_language(cls, v):
        if not v or len(v) < 2 or len(v) > 3:
            raise ValueError("Language code must be 2-3 characters")
        return v

    @validator("samplingRate")
    def validate_sampling_rate(cls, v):
        if not 8000 <= v <= 48000:
            raise ValueError("Sampling rate must be between 8000 and 48000 Hz")
        return v

    @validator("responseFrequencyInMs")
    def validate_response_frequency(cls, v):
        if v < 100:
            raise ValueError("Response frequency must be at least 100ms")
        return v


class StreamingAudioResponse(BaseModel):
    """Audio response for TTS streaming."""
    audioContent: str
    isFinal: bool
    duration: Optional[float] = None
    timestamp: float
    format: str


@dataclass
class StreamingTTSSessionState:
    """Session state for TTS streaming."""
    session_id: str
    config: StreamingTTSConfig
    text_buffer: str = ""
    api_key: Optional[str] = None
    user_id: Optional[int] = None
    api_key_id: Optional[int] = None
    request_id: Optional[str] = None
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def reset_buffer(self) -> None:
        self.text_buffer = ""

    def add_text(self, text: str) -> None:
        self.text_buffer += text

    def get_text_chunks(self, max_length: int = 400) -> List[str]:
        if not self.text_buffer:
            return []
        if len(self.text_buffer) <= max_length:
            return [self.text_buffer]
        chunks = []
        text = self.text_buffer
        while len(text) > max_length:
            break_point = max_length
            for i in range(max_length - 1, max_length // 2, -1):
                if text[i] in " \n\t.,!?;:":
                    break_point = i + 1
                    break
            chunks.append(text[:break_point].strip())
            text = text[break_point:].strip()
        if text:
            chunks.append(text)
        return chunks


class StreamingTTSService:
    """TTS streaming service using Socket.IO for real-time text-to-speech."""

    def __init__(
        self,
        audio_service: AudioService,
        text_service: TextService,
        triton_client: TTSTritonClient,
        repository: TTSRepository,
        voice_service: VoiceService,
        redis_client,
        response_frequency_in_ms: int = 2000,
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

        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.app = socketio.ASGIApp(self.sio, socketio_path="")

        self.client_states: Dict[str, StreamingTTSSessionState] = {}

        self.configure_socket_server()

    def configure_socket_server(self):
        """Configure Socket.IO event handlers."""

        @self.sio.event
        async def connect(sid: str, environ: dict, auth):
            try:
                query_string = environ.get("QUERY_STRING", "")
                query_params = self._parse_query_string(query_string)

                service_id = query_params.get("serviceId")
                voice_id = query_params.get("voice_id")
                language = query_params.get("language")
                gender = query_params.get("gender")

                if not all([service_id, voice_id, language, gender]):
                    await self.sio.emit("error", {
                        "error": "Missing required parameters: serviceId, voice_id, language, gender",
                        "code": "MISSING_PARAMETERS",
                        "timestamp": time.time(),
                    }, room=sid)
                    return False

                try:
                    model_id, resolved_gender = self.voice_service.resolve_voice(voice_id)
                except VoiceNotFoundError:
                    await self.sio.emit("error", {
                        "error": f"Voice not found: {voice_id}",
                        "code": "VOICE_NOT_FOUND",
                        "timestamp": time.time(),
                    }, room=sid)
                    return False

                sampling_rate = int(query_params.get("samplingRate", 22050))
                audio_format = query_params.get("audioFormat", "wav")

                config = StreamingTTSConfig(
                    serviceId=service_id,
                    voice_id=voice_id,
                    language=language,
                    gender=gender,
                    samplingRate=sampling_rate,
                    audioFormat=audio_format,
                )

                await self.initialize_session_state(sid, config, None, None, None)
                logger.info(f"TTS streaming client connected: {sid}")
                return True
            except Exception as e:
                logger.error(f"Connection error for {sid}: {e}")
                await self.sio.emit("error", {
                    "error": f"Connection failed: {str(e)}",
                    "code": "CONNECTION_FAILED",
                    "timestamp": time.time(),
                }, room=sid)
                return False

        @self.sio.on("start")
        async def start(sid: str, config_update: Optional[Dict] = None):
            try:
                if sid not in self.client_states:
                    await self.sio.emit("error", {
                        "error": "Session not found",
                        "code": "SESSION_NOT_FOUND",
                        "timestamp": time.time(),
                    }, room=sid)
                    return

                state = self.client_states[sid]
                if config_update:
                    if "responseFrequencyInMs" in config_update:
                        state.config.responseFrequencyInMs = config_update["responseFrequencyInMs"]
                    if "audioFormat" in config_update:
                        state.config.audioFormat = config_update["audioFormat"]

                state.reset_buffer()
                await self.sio.emit("ready", room=sid)
                logger.info(f"TTS stream started: {sid}")
            except Exception as e:
                logger.error(f"Start error for {sid}: {e}")
                await self.sio.emit("error", {
                    "error": f"Start failed: {str(e)}",
                    "code": "START_FAILED",
                    "timestamp": time.time(),
                }, room=sid)

        @self.sio.on("data")
        async def data(sid: str, text: str, is_final: bool = False, disconnect_stream: bool = False):
            try:
                if sid not in self.client_states:
                    await self.sio.emit("error", {
                        "error": "Session not found",
                        "code": "SESSION_NOT_FOUND",
                        "timestamp": time.time(),
                    }, room=sid)
                    return

                state = self.client_states[sid]
                if text:
                    state.add_text(text)

                if is_final or disconnect_stream:
                    if state.text_buffer.strip():
                        await self.synthesize_and_emit(sid, is_final)

                if disconnect_stream:
                    await self.delete_session_state(sid)
                    await self.sio.emit("terminate", room=sid)
                    logger.info(f"TTS stream terminated: {sid}")
            except Exception as e:
                logger.error(f"Data error for {sid}: {e}")
                await self.sio.emit("error", {
                    "error": f"Data processing failed: {str(e)}",
                    "code": "DATA_PROCESSING_FAILED",
                    "timestamp": time.time(),
                }, room=sid)

        @self.sio.event
        def disconnect(sid: str):
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
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value
        return params

    async def initialize_session_state(
        self,
        sid: str,
        config: StreamingTTSConfig,
        api_key: Optional[str],
        user_id: Optional[int],
        api_key_id: Optional[int],
    ):
        """Initialize session state and create database request."""
        try:
            request_id = str(uuid4())
            state = StreamingTTSSessionState(
                session_id=sid,
                config=config,
                api_key=api_key,
                user_id=user_id,
                api_key_id=api_key_id,
                request_id=request_id,
            )
            self.client_states[sid] = state
            logger.info(f"Session state initialized: {sid}")
        except Exception as e:
            logger.error(f"Failed to initialize session state for {sid}: {e}")
            raise

    async def delete_session_state(self, sid: str):
        """Delete session state and update database."""
        try:
            if sid in self.client_states:
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

            total_duration = await self.run_tts_inference(sid)

            response = StreamingAudioResponse(
                audioContent="",
                isFinal=is_final,
                duration=total_duration,
                timestamp=time.time(),
                format=state.config.audioFormat,
            )
            await self.sio.emit("response", data=response.dict(), room=sid)
            state.reset_buffer()
            logger.info(f"Audio synthesized and emitted: {sid}, duration: {total_duration:.2f}s")
        except Exception as e:
            logger.error(f"Synthesis error for {sid}: {e}")
            await self.sio.emit("error", {
                "error": f"Synthesis failed: {str(e)}",
                "code": "SYNTHESIS_FAILED",
                "timestamp": time.time(),
            }, room=sid)

    async def run_tts_inference(self, sid: str) -> float:
        """Run TTS inference on buffered text."""
        state = self.client_states[sid]
        total_duration = 0.0

        try:
            text_chunks = state.get_text_chunks(max_length=400)

            for i, chunk in enumerate(text_chunks):
                if not chunk.strip():
                    continue

                processed_text = self.text_service.process_tts_input(chunk)
                model_id, gender = self.voice_service.resolve_voice(state.config.voice_id)

                inputs, outputs = self.triton_client.get_tts_io_for_triton(
                    processed_text, gender, state.config.language
                )
                response = self.triton_client.send_triton_request("tts", input_list=inputs, output_list=outputs)
                raw_audio = response.as_numpy("OUTPUT_GENERATED_AUDIO")[0]

                target_sr = state.config.samplingRate
                if target_sr != 22050:
                    raw_audio = self.audio_service.resample_audio(raw_audio, 22050, target_sr)

                audio_base64 = base64.b64encode(raw_audio).decode("utf-8")
                duration = len(raw_audio) / target_sr
                total_duration += duration

                chunk_response = StreamingAudioResponse(
                    audioContent=audio_base64,
                    isFinal=(i == len(text_chunks) - 1),
                    duration=duration,
                    timestamp=time.time(),
                    format=state.config.audioFormat,
                )
                await self.sio.emit("response", data=chunk_response.dict(), room=sid)

                if i < len(text_chunks) - 1:
                    await asyncio.sleep(0.1)

            return total_duration
        except Exception as e:
            logger.error(f"TTS inference error for {sid}: {e}")
            raise
