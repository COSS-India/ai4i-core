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

from app.schemas.inference import (
    StreamingConfig,
    StreamingAudioChunk,
    StreamingResponse,
    StreamingError,
)
from app.services.audio_service import AudioService
from app.clients.triton_client import ASRTritonClient
from app.repositories.asr_repository import ASRRepository
from ai4icore_env import app_env
from app.dependencies.auth import validate_api_key_jwt

logger = logging.getLogger(__name__)


class StreamingSessionState:
    """Session state for a streaming ASR connection."""

    def __init__(
        self,
        session_id: str,
        config: StreamingConfig,
        api_key: Optional[str] = None,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        run_inference_once_in_bytes: int = 0,
        request_id=None,
    ):
        self.session_id = session_id
        self.config = config
        self.api_key = api_key
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.run_inference_once_in_bytes = run_inference_once_in_bytes
        self.request_id = request_id
        self.buffer = b""
        self.history: list = []
        self.last_inference_position = 0

    def should_run_inference(self) -> bool:
        return len(self.buffer) - self.last_inference_position >= self.run_inference_once_in_bytes

    def update_inference_position(self):
        self.last_inference_position = len(self.buffer)

    def add_to_history(self, transcript: str):
        self.history.append(transcript)

    def reset_buffer(self):
        self.buffer = b""
        self.last_inference_position = 0


class StreamingASRService:
    """Socket.IO based streaming ASR service."""

    def __init__(
        self,
        audio_service: AudioService,
        triton_client: ASRTritonClient,
        repository: ASRRepository,
        redis_client,
        response_frequency_in_ms: int = 2000,
        bytes_per_sample: int = 2,
    ):
        self.audio_service = audio_service
        self.triton_client = triton_client
        self.repository = repository
        self.redis_client = redis_client
        self.response_frequency_in_ms = response_frequency_in_ms
        self.bytes_per_sample = bytes_per_sample

        self.sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins="*",
            logger=True,
            engineio_logger=True,
        )
        self.app = socketio.ASGIApp(self.sio, socketio_path="/socket.io")

        self.client_states: Dict[str, StreamingSessionState] = {}

        self.configure_socket_server()

    def configure_socket_server(self) -> None:
        """Configure Socket.IO event handlers."""

        @self.sio.event
        async def connect(sid: str, environ: dict, auth):
            try:
                query_string = environ.get("QUERY_STRING", "")
                query_params = urllib.parse.parse_qs(query_string)

                service_id = query_params.get("serviceId", [None])[0]
                language = query_params.get("language", [None])[0]
                sampling_rate = query_params.get("samplingRate", ["16000"])[0]
                api_key = None
                if isinstance(auth, dict) and auth.get("token"):
                    api_key = auth["token"]
                if not api_key:
                    api_key = query_params.get("apiKey", [None])[0]

                preprocessors = query_params.get("preProcessors", [None])[0]
                postprocessors = query_params.get("postProcessors", [None])[0]

                if not service_id or not language:
                    error = StreamingError(
                        error="Missing required parameters: serviceId and language are required",
                        code="MISSING_PARAMETERS",
                    )
                    await self.sio.emit("error", data=error.dict(), room=sid)
                    return False

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

                auth_enabled = (app_env.auth_enabled or "true").lower() == "true"
                require_api_key = (app_env.require_api_key or "true").lower() == "true"
                allow_anonymous = app_env.allow_anonymous_access

                user_id = None
                api_key_id = None
                if auth_enabled and require_api_key and api_key:
                    try:
                        result = await validate_api_key_jwt(api_key)
                        user_id = result.user_id
                    except Exception as e:
                        logger.error(f"Authentication failed for streaming connection: {e}")
                        await self.sio.emit("error", {"error": "Authentication failed", "code": "AUTH_ERROR"}, room=sid)
                        return False
                elif auth_enabled and require_api_key and not api_key and not allow_anonymous:
                    logger.error("API key required but not provided for streaming connection")
                    await self.sio.emit("error", {"error": "API key required", "code": "AUTH_ERROR"}, room=sid)
                    return False

                config = StreamingConfig(
                    serviceId=service_id,
                    language=language,
                    samplingRate=int(sampling_rate),
                    preProcessors=preprocessors_list,
                    postProcessors=postprocessors_list,
                    enableVAD="vad" in (preprocessors_list or []),
                )

                await self.initialize_session_state(sid, config, api_key, user_id, api_key_id)

                logger.info(f"Client connected: {sid} with config: {config.serviceId}, {config.language}")
                return True

            except Exception as e:
                logger.error(f"Connection error for session {sid}: {e}")
                error = StreamingError(error=f"Connection failed: {str(e)}", code="CONNECTION_ERROR")
                await self.sio.emit("error", data=error.dict(), room=sid)
                return False

        @self.sio.on("start")
        async def start(sid: str, config_update: Optional[Dict] = None):
            try:
                if sid not in self.client_states:
                    await self.sio.emit(
                        "error",
                        data={"error": "Session not found", "code": "SESSION_NOT_FOUND", "timestamp": time.time()},
                        room=sid,
                    )
                    return

                if config_update:
                    state = self.client_states[sid]
                    if "responseFrequencyInMs" in config_update:
                        state.config.responseFrequencyInMs = config_update["responseFrequencyInMs"]
                        state.run_inference_once_in_bytes = int(
                            state.config.samplingRate * (state.config.responseFrequencyInMs / 1000) * self.bytes_per_sample
                        )

                self.reset_buffer(sid)
                await self.sio.emit("ready", room=sid)
                logger.info(f"Stream started for session: {sid}")

            except Exception as e:
                logger.error(f"Start error for session {sid}: {e}")
                await self.sio.emit(
                    "error",
                    data={"error": f"Start failed: {str(e)}", "code": "START_ERROR", "timestamp": time.time()},
                    room=sid,
                )

        @self.sio.on("data")
        async def data(sid: str, audio_data: bytes, is_speaking: bool, disconnect_stream: bool):
            try:
                if sid not in self.client_states:
                    await self.sio.emit(
                        "error",
                        data={"error": "Session not found", "code": "SESSION_NOT_FOUND", "timestamp": time.time()},
                        room=sid,
                    )
                    return

                state = self.client_states[sid]
                state.buffer += audio_data

                if not is_speaking and len(state.buffer) > 0:
                    transcript = await self.transcribe_and_emit(sid, is_final=True)
                    if transcript:
                        state.add_to_history(transcript)
                    self.reset_buffer(sid)

                elif is_speaking and state.should_run_inference():
                    await self.transcribe_and_emit(sid, is_final=False)
                    state.update_inference_position()

                if disconnect_stream:
                    if len(state.buffer) > 0:
                        transcript = await self.transcribe_and_emit(sid, is_final=True)
                        if transcript:
                            state.add_to_history(transcript)

                    if state.request_id:
                        await self.repository.update_request_status(state.request_id, "completed")

                    self.delete_session_state(sid)
                    await self.sio.emit("terminate", room=sid)
                    logger.info(f"Stream terminated for session: {sid}")

            except Exception as e:
                logger.error(f"Data processing error for session {sid}: {e}")
                await self.sio.emit(
                    "error",
                    data={"error": f"Data processing failed: {str(e)}", "code": "DATA_PROCESSING_ERROR", "timestamp": time.time()},
                    room=sid,
                )

        @self.sio.event
        def disconnect(sid: str):
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
        api_key_id: Optional[int] = None,
    ) -> None:
        """Initialize session state for a new connection."""
        try:
            run_inference_once_in_bytes = int(
                config.samplingRate * (config.responseFrequencyInMs / 1000) * self.bytes_per_sample
            )

            request_id = None
            if self.repository:
                request_id = await self.repository.create_request(
                    model_id=config.serviceId,
                    language=config.language,
                    status="streaming",
                    user_id=user_id,
                    api_key_id=api_key_id,
                )

            state = StreamingSessionState(
                session_id=sid,
                config=config,
                api_key=api_key,
                user_id=user_id,
                api_key_id=api_key_id,
                run_inference_once_in_bytes=run_inference_once_in_bytes,
                request_id=request_id,
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
                if state.request_id and self.repository:
                    asyncio.create_task(self.repository.update_request_status(state.request_id, "disconnected"))
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

            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

            if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
                audio_array = self.audio_service.stereo_to_mono(audio_array)

            if config.samplingRate != 16000:
                audio_array = self.audio_service.resample_audio(audio_array, config.samplingRate, 16000)

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

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(config.samplingRate)
                wav_file.writeframes(state.buffer)

            wav_buffer.seek(0)
            audio_data, sample_rate = sf.read(wav_buffer, dtype="float32")

            audio_array = self.process_audio_chunk(sid, state.buffer)

            inputs, outputs = self.triton_client.get_asr_io_for_triton(
                [audio_array], config.serviceId, config.language
            )

            model_name = config.serviceId
            response = self.triton_client.send_triton_request(model_name, inputs, outputs)

            transcript = response.as_numpy("TRANSCRIPTS")[0].decode("utf-8")
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

            transcript = await self.run_inference_from_buffer(sid)
            if not transcript:
                return None

            if is_final:
                state.add_to_history(transcript)

            response = StreamingResponse(
                transcript=transcript,
                isFinal=is_final,
                language=state.config.language,
                timestamp=time.time(),
            )

            await self.sio.emit("response", data=response.dict(), room=sid)

            logger.debug(f"Emitted transcript for {sid}: {transcript[:50]}... (final={is_final})")
            return transcript

        except Exception as e:
            logger.error(f"Transcription error for session {sid}: {e}")
            error = StreamingError(error=f"Transcription failed: {str(e)}", code="INFERENCE_FAILED")
            await self.sio.emit("error", data=error.dict(), room=sid)
            return None
