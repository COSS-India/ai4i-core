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

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse, AudioOutput, AudioConfig
from repositories.tts_repository import TTSRepository
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient, TritonInferenceError
from ai4icore_model_management import ModelManagementClient, ServiceInfo
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Custom exception for Triton inference errors."""
    pass


class TTSService:
    """Main TTS service for text-to-speech inference."""
    
    def __init__(
        self,
        repository: TTSRepository,
        audio_service: AudioService,
        text_service: TextService,
        get_triton_client_func,
        model_management_client: ModelManagementClient,
        redis_client=None,
        cache_ttl_seconds: int = 300
    ):
        """Initialize TTS service with dependencies."""
        if model_management_client is None:
            raise ValueError("model_management_client is required. Model management service must be available.")
        
        self.repository = repository
        self.audio_service = audio_service
        self.text_service = text_service
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._triton_clients: Dict[str, TritonClient] = {}
        
        # Service info cache (service_id -> (ServiceInfo, expires_at))
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
        
        # Service registry cache (service_id -> (endpoint, model_name, expires_at))
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
    
    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> ServiceInfo:
        """Get service info from model management service with caching"""
        # Check cache first
        cached = self._service_info_cache.get(service_id)
        if cached:
            service_info, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service info cache hit for {service_id}")
                return service_info
            self._service_info_cache.pop(service_id, None)
        
        # Fetch from model management service (REQUIRED)
        try:
            logger.info(f"Fetching service info for {service_id} from model management service")
            service_info = await self.model_management_client.get_service(
                service_id,
                use_cache=True,
                redis_client=self.redis_client,
                auth_headers=auth_headers
            )
            
            if service_info is None:
                error_msg = (
                    f"Service ID '{service_id}' not found in model management service. "
                    f"Please verify the service ID is correct and register the service in the model management service."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            if not service_info.endpoint:
                error_msg = (
                    f"Service ID '{service_id}' has no Triton endpoint configured in model management service. "
                    f"Please configure the endpoint for this service."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Cache the service info
            expires_at = time.time() + self.cache_ttl_seconds
            self._service_info_cache[service_id] = (service_info, expires_at)
            
            # Also update registry cache
            endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            
            logger.info(f"Successfully fetched and cached service info for {service_id}")
            return service_info
            
        except ValueError:
            raise
        except Exception as e:
            error_msg = (
                f"Failed to fetch service info for service ID '{service_id}' from model management service: {e}. "
                f"Please verify the model management service is available and the service ID is correct."
            )
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    
    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str) -> Tuple[str, str]:
        """Extract Triton endpoint and model name from ServiceInfo"""
        # Extract endpoint (remove http:// or https:// prefix if present)
        endpoint = service_info.endpoint or ""
        endpoint = endpoint.replace("http://", "").replace("https://", "").strip()
        
        # Extract model name - try multiple sources
        model_name = service_info.triton_model or "tts"
        
        # Check model_inference_endpoint for model name
        if service_info.model_inference_endpoint:
            if isinstance(service_info.model_inference_endpoint, dict):
                endpoint_model_name = service_info.model_inference_endpoint.get("modelName") or service_info.model_inference_endpoint.get("model_name")
                if endpoint_model_name:
                    model_name = endpoint_model_name
        
        logger.info(f"Extracted Triton metadata for {service_id}: endpoint={endpoint}, model_name={model_name}")
        return endpoint, model_name
    
    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        """Get service registry entry (endpoint, model_name) for the given service ID"""
        # Check registry cache first
        cached = self._service_registry_cache.get(service_id)
        if cached:
            endpoint, model_name, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service registry cache hit for {service_id}")
                return (endpoint, model_name)
            self._service_registry_cache.pop(service_id, None)
        
        # Get from model management service (REQUIRED)
        service_info = await self._get_service_info(service_id, auth_headers)
        endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
        return (endpoint, model_name)
    
    async def get_triton_client(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> TritonClient:
        """Get Triton client for the given service ID"""
        # Check cache first
        if service_id in self._triton_clients:
            logger.debug(f"Triton client cache hit for {service_id}")
            return self._triton_clients[service_id]
        
        # Get endpoint from model management service (REQUIRED)
        endpoint, _ = await self._get_service_registry_entry(service_id, auth_headers)
        
        # Create client using factory function
        logger.info(f"Creating Triton client for service {service_id} with endpoint {endpoint}")
        client = self.get_triton_client_func(endpoint)
        self._triton_clients[service_id] = client
        return client
    
    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        """Get Triton model name based on service ID"""
        _, model_name = await self._get_service_registry_entry(service_id, auth_headers)
        return model_name
    
    async def run_inference(
        self,
        request: TTSInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> TTSInferenceResponse:
        """
        Run TTS inference for the given request.
        
        Adapted from Dhruva-Platform-2 run_tts_triton_inference method.
        """
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
            
            # Get Triton client and model name dynamically from model management
            triton_client = await self.get_triton_client(service_id, auth_headers)
            model_name = await self.get_model_name(service_id, auth_headers)
            
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
                            inputs, outputs = triton_client.get_tts_io_for_triton(
                                text=chunk,
                                gender=gender,
                                language=language
                            )
                            
                            # Send Triton request
                            triton_response = triton_client.send_triton_request(
                                model_name=model_name,
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
            
            logger.info(f"TTS inference completed successfully in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"TTS inference failed: {e}")
            
            # Update request status to failed
            if 'request_id' in locals():
                await self.repository.update_request_status(
                    request_id, "failed", error_message=str(e)
                )
            
            raise
