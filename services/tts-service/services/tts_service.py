"""
Main TTS service class containing core inference logic.

Adapted from Dhruva-Platform-2 run_tts_triton_inference method (lines 468-592).
"""

import asyncio
import base64
import json
import logging
import time
from io import BytesIO
from typing import Optional, List, Dict, Tuple
import numpy as np
from scipy.io import wavfile
from pydub import AudioSegment

from models.tts_request import TTSInferenceRequest
from models.tts_response import TTSInferenceResponse, AudioOutput, AudioConfig
from repositories.tts_repository import TTSRepository
from services.audio_service import AudioService
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient, ServiceInfo

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
        default_triton_client: Optional[TritonClient],
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client = None,
        cache_ttl_seconds: int = 300
    ):
        """Initialize TTS service with dependencies."""
        self.repository = repository
        self.audio_service = audio_service
        self.text_service = text_service
        self.default_triton_client = default_triton_client
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_prefix = "tts:triton"
        # Cache Triton clients and service metadata with TTL so we can refresh on endpoint move
        self._triton_clients: Dict[str, Tuple[TritonClient, str, float]] = {}
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
    
    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[ServiceInfo]:
        """Get service info from model management service with caching"""
        # Check cache first
        cached = self._service_info_cache.get(service_id)
        if cached:
            service_info, expires_at = cached
            if expires_at > time.time():
                return service_info
            # Expired entry
            self._service_info_cache.pop(service_id, None)
        
        # Fetch from model management service if client is available
        if self.model_management_client:
            try:
                service_info = await self.model_management_client.get_service(
                    service_id,
                    use_cache=True,
                    redis_client=self.redis_client,
                    auth_headers=auth_headers
                )
                if service_info:
                    expires_at = time.time() + self.cache_ttl_seconds
                    self._service_info_cache[service_id] = (service_info, expires_at)
                    # Also update registry cache
                    if service_info.endpoint:
                        endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
                        self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
                return service_info
            except Exception as e:
                logger.warning(
                    f"Failed to fetch service info for {service_id} from model management service: {e}. "
                    "Will use default Triton client as fallback."
                )
                # Fallback to default behavior - return None to use default client
                return None
        else:
            logger.debug("Model management client not available, using default Triton client")
        
        return None
    
    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, str]]:
        """Get service registry entry (endpoint, model_name) for service_id"""
        # Check local cache first
        cached = self._service_registry_cache.get(service_id)
        if cached:
            endpoint, model_name, expires_at = cached
            if expires_at > time.time():
                return endpoint, model_name
            self._service_registry_cache.pop(service_id, None)

        # Check Redis cache (shared across instances)
        redis_entry = await self._get_registry_from_redis(service_id)
        if redis_entry:
            endpoint, model_name = redis_entry
            expires_at = time.time() + self.cache_ttl_seconds
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            return endpoint, model_name
        
        # Fetch from model management service
        service_info = await self._get_service_info(service_id, auth_headers)
        if service_info and service_info.endpoint:
            endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
            expires_at = time.time() + self.cache_ttl_seconds
            entry = (endpoint, model_name)
            self._service_registry_cache[service_id] = (endpoint, model_name, expires_at)
            await self._set_registry_in_redis(service_id, endpoint, model_name)
            return entry
        
        return None
    
    async def get_triton_client(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> TritonClient:
        """Get Triton client for the given service ID with fallback to default"""
        # Check cache first
        cached_client = self._triton_clients.get(service_id)
        if cached_client:
            client, endpoint, expires_at = cached_client
            if expires_at > time.time():
                # Verify endpoint did not change in shared cache
                service_entry = await self._get_service_registry_entry(service_id, auth_headers)
                if service_entry and service_entry[0] != endpoint:
                    # Endpoint changed; drop cached client and rebuild below
                    self._triton_clients.pop(service_id, None)
                else:
                    return client
            else:
                self._triton_clients.pop(service_id, None)
        
        # Get endpoint and model info from model management service
        try:
            service_entry = await self._get_service_registry_entry(service_id, auth_headers)
            if service_entry:
                endpoint, _ = service_entry
                # Create client using factory function if available
                if self.get_triton_client_func:
                    client = self.get_triton_client_func(endpoint)
                    expires_at = time.time() + self.cache_ttl_seconds
                    self._triton_clients[service_id] = (client, endpoint, expires_at)
                    return client
        except Exception as e:
            logger.warning(
                f"Error getting service registry entry for {service_id}: {e}. "
                "Falling back to default Triton client."
            )
        
        # Fallback to default client if service not found or error occurred
        if self.default_triton_client:
            logger.debug(f"Using default Triton client for service {service_id}")
            return self.default_triton_client
        raise TritonInferenceError(
            f"No Triton endpoint available for service {service_id} and no default client configured."
        )
    
    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        """Get Triton model name based on service ID with fallback"""
        try:
            service_entry = await self._get_service_registry_entry(service_id, auth_headers)
            if service_entry:
                model_name = service_entry[1]  # Return model name
                if model_name and model_name != "unknown":
                    return model_name
        except Exception as e:
            logger.debug(f"Error getting model name for {service_id}: {e}")
        
        # Try to extract from service_id as last resort
        # e.g., "ai4bharat/indic-tts-coqui--gpu-t4" -> "tts"
        parts = service_id.split("/")
        if len(parts) > 1:
            model_part = parts[-1]
        else:
            model_part = service_id
        
        if "--" in model_part:
            return model_part.split("--")[0]
        
        # Final fallback: return "tts" instead of service_id for TTS models
        logger.warning(f"Could not determine model name for {service_id}, using 'tts' as fallback")
        return "tts"

    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str = None) -> Tuple[str, str]:
        """Extract normalized Triton endpoint and model name from service info"""
        endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
        model_name = service_info.triton_model

        # Try to infer model name from model inference endpoint metadata when provided
        if service_info.model_inference_endpoint:
            # Common keys we might see; keep this flexible for future providers
            model_name = (
                service_info.model_inference_endpoint.get("model_name")
                or service_info.model_inference_endpoint.get("modelName")
                or service_info.model_inference_endpoint.get("model")
                or model_name
            )
        
        # If still no model name, try to extract from service_id as fallback
        # e.g., "ai4bharat/indic-tts-coqui--gpu-t4" -> "tts"
        if not model_name and service_id:
            # Extract model name from service_id (format: "org/model--variant" or "model--variant")
            parts = service_id.split("/")
            if len(parts) > 1:
                model_part = parts[-1]  # Get last part after "/"
            else:
                model_part = service_id
            
            # Remove variant suffix (e.g., "--gpu-t4" -> "tts")
            if "--" in model_part:
                model_name = model_part.split("--")[0]
            else:
                model_name = model_part
        
        # Final fallback: use "tts" as default for TTS models
        if not model_name:
            model_name = "tts"
            logger.warning(
                f"Could not determine Triton model name for service {service_id}. "
                f"Using default 'tts'."
            )
        
        return endpoint, model_name

    async def _get_registry_from_redis(self, service_id: str) -> Optional[Tuple[str, str]]:
        """Read shared registry entry (endpoint, model) from Redis"""
        if not self.redis_client:
            return None
        try:
            cache_key = f"{self.cache_prefix}:registry:{service_id}"
            cached = await self.redis_client.get(cache_key)
            if cached:
                data = json.loads(cached)
                endpoint = data.get("endpoint")
                model_name = data.get("model_name")
                if endpoint and model_name:
                    return endpoint, model_name
        except Exception as e:
            logger.warning(f"Redis read failed for service {service_id}: {e}")
        return None

    async def _set_registry_in_redis(self, service_id: str, endpoint: str, model_name: str):
        """Write shared registry entry (endpoint, model) to Redis with TTL"""
        if not self.redis_client:
            return
        try:
            cache_key = f"{self.cache_prefix}:registry:{service_id}"
            payload = json.dumps({"endpoint": endpoint, "model_name": model_name})
            await self.redis_client.setex(cache_key, self.cache_ttl_seconds, payload)
        except Exception as e:
            logger.warning(f"Redis write failed for service {service_id}: {e}")
    
    async def invalidate_cache(self, service_id: str):
        """
        Invalidate all cache layers for a specific service_id.
        
        This clears:
        1. TTS Service in-memory caches (_service_info_cache, _service_registry_cache, _triton_clients)
        2. TTS Service Redis cache (tts:triton:registry:{serviceId})
        3. Model Management Client caches (via clear_cache)
        
        Use this when you know the endpoint has changed in Model Management DB
        and you want to force a refresh on the next request.
        """
        # Clear in-memory caches
        self._service_info_cache.pop(service_id, None)
        self._service_registry_cache.pop(service_id, None)
        self._triton_clients.pop(service_id, None)
        
        # Clear Redis cache
        if self.redis_client:
            try:
                cache_key = f"{self.cache_prefix}:registry:{service_id}"
                await self.redis_client.delete(cache_key)
                logger.info(f"Invalidated Redis cache for service {service_id}")
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache for {service_id}: {e}")
        
        # Clear model management client cache
        if self.model_management_client:
            try:
                self.model_management_client.clear_cache(self.redis_client)
                logger.info(f"Invalidated model management client cache")
            except Exception as e:
                logger.warning(f"Failed to invalidate model management client cache: {e}")
    
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
            
            # Resolve model name and Triton client dynamically
            model_name = await self.get_model_name(service_id, auth_headers)
            triton_client = await self.get_triton_client(service_id, auth_headers)
            
            logger.info(f"Using Triton model '{model_name}' for service '{service_id}'")
            
            # Convert PCM format to s16le for Triton
            if audio_format == "pcm":
                format_str = "s16le"
            else:
                format_str = audio_format
            
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
                            inputs, outputs = triton_client.get_tts_io_for_triton(
                                text=chunk,
                                gender=gender,
                                language=language
                            )
                            
                            # Send Triton request with dynamically resolved model name
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
                    if format_str != "wav":
                        audio_segment = AudioSegment.from_file(byte_io, format="wav")
                        byte_io = BytesIO()
                        audio_segment.export(byte_io, format=format_str)
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
                audio_format=format_str,
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
