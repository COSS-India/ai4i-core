"""
NMT Service
Main NMT service containing core inference logic
"""

import time
import json
import logging
from typing import Optional, List, Dict, Tuple
from uuid import UUID

import numpy as np

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse, TranslationOutput
from repositories.nmt_repository import NMTRepository
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient, ServiceInfo
from middleware.exceptions import (
    TritonInferenceError,
    TextProcessingError,
    ModelNotFoundError,
    ServiceUnavailableError
)

logger = logging.getLogger(__name__)


class NMTService:
    """Main NMT service for translation inference"""
    
    # Language code to script code mapping
    LANG_CODE_TO_SCRIPT_CODE = {
        "hi": "Deva", "ur": "Arab", "ta": "Taml", "te": "Telu", 
        "kn": "Knda", "ml": "Mlym", "bn": "Beng", "gu": "Gujr", 
        "mr": "Deva", "pa": "Guru", "or": "Orya", "as": "Beng"
    }
    
    def __init__(
        self,
        repository: NMTRepository,
        text_service: TextService,
        default_triton_client: Optional[TritonClient],
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client = None,
        cache_ttl_seconds: int = 300
    ):
        self.repository = repository
        self.text_service = text_service
        self.default_triton_client = default_triton_client
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_prefix = "nmt:triton"
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
                # Apply mapping: "indictrans" -> "nmt" for Triton server
                if model_name == "indictrans":
                    logger.info(f"Mapped local cached model name 'indictrans' to 'nmt' for Triton (service_id: {service_id})")
                    model_name = "nmt"
                return endpoint, model_name
            self._service_registry_cache.pop(service_id, None)

        # Check Redis cache (shared across instances)
        redis_entry = await self._get_registry_from_redis(service_id)
        if redis_entry:
            endpoint, model_name = redis_entry
            # Apply mapping: "indictrans" -> "nmt" for Triton server
            if model_name == "indictrans":
                logger.info(f"Mapped Redis cached model name 'indictrans' to 'nmt' for Triton (service_id: {service_id})")
                model_name = "nmt"
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
        model_name = None
        
        try:
            service_entry = await self._get_service_registry_entry(service_id, auth_headers)
            if service_entry:
                model_name = service_entry[1]  # Return model name
                if model_name and model_name != "unknown":
                    # Apply mapping: "indictrans" -> "nmt" for Triton server
                    if model_name == "indictrans":
                        logger.info(f"Mapped cached model name 'indictrans' to 'nmt' for Triton (service_id: {service_id})")
                        return "nmt"
                    return model_name
        except Exception as e:
            logger.debug(f"Error getting model name for {service_id}: {e}")
        
        # Special case: if service_id is "indictrans", use "nmt" as the model name
        # This is because the Triton server has the model named "nmt", not "indictrans"
        if service_id == "indictrans":
            logger.info(f"Service ID '{service_id}' maps to Triton model 'nmt'")
            return "nmt"
        
        # Try to extract from service_id as last resort
        # e.g., "ai4bharat/indictrans--gpu-t4" -> "indictrans"
        parts = service_id.split("/")
        if len(parts) > 1:
            model_part = parts[-1]
        else:
            model_part = service_id
        
        if "--" in model_part:
            extracted = model_part.split("--")[0]
            # If extracted name is "indictrans", use "nmt" instead
            if extracted == "indictrans":
                logger.info(f"Extracted model name '{extracted}' from service_id '{service_id}', using 'nmt' for Triton")
                return "nmt"
            return extracted
        
        # Final fallback: if service_id is "indictrans", use "nmt"
        if service_id == "indictrans":
            return "nmt"
        
        # Final fallback: return the service_id itself (better than "nmt" task type)
        logger.warning(f"Could not determine model name for {service_id}, using service_id as fallback")
        return service_id

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
        # e.g., "ai4bharat/indictrans--gpu-t4" -> "indictrans"
        if not model_name and service_id:
            # Extract model name from service_id (format: "org/model--variant" or "model--variant")
            parts = service_id.split("/")
            if len(parts) > 1:
                model_part = parts[-1]  # Get last part after "/"
            else:
                model_part = service_id
            
            # Remove variant suffix (e.g., "--gpu-t4" -> "indictrans")
            if "--" in model_part:
                model_name = model_part.split("--")[0]
            else:
                model_name = model_part
        
        # Special case: map "indictrans" to "nmt" for Triton server
        # The Triton server has the model named "nmt", not "indictrans"
        if model_name == "indictrans":
            logger.info(f"Mapped model name 'indictrans' to 'nmt' for Triton server (service_id: {service_id})")
            model_name = "nmt"
        
        # Final fallback: use a placeholder that indicates unknown (not task type)
        if not model_name:
            model_name = "unknown"
            logger.warning(
                f"Could not determine Triton model name for service {service_id}. "
                f"Using placeholder 'unknown'. Please ensure Model Management provides model name."
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
        1. NMT Service in-memory caches (_service_info_cache, _service_registry_cache, _triton_clients)
        2. NMT Service Redis cache (nmt:triton:registry:{serviceId})
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
        
        # Clear Model Management Client cache
        if self.model_management_client:
            try:
                # Model Management uses key: model_mgmt:service:{serviceId}
                model_mgmt_key = f"model_mgmt:service:{service_id}"
                if self.redis_client:
                    await self.redis_client.delete(model_mgmt_key)
                # Also clear in-memory cache in Model Management Client
                # (Note: ModelManagementClient.clear_cache() clears all, not per-service)
                logger.info(f"Invalidated Model Management cache for service {service_id}")
            except Exception as e:
                logger.warning(f"Failed to invalidate Model Management cache for {service_id}: {e}")
        
        logger.info(f"Cache invalidated for service {service_id} across all layers")
    
    async def run_inference(
        self,
        request: NMTInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> NMTInferenceResponse:
        """Run NMT inference on the given request"""
        start_time = time.time()
        request_id = None
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            source_lang = request.config.language.sourceLanguage
            target_lang = request.config.language.targetLanguage
            
            # Get model name dynamically based on service ID
            model_name = await self.get_model_name(service_id, auth_headers)
            
            # Store original languages for response
            original_source_lang = source_lang
            original_target_lang = target_lang
            
            # Handle script codes - only append if explicitly provided in request
            if request.config.language.sourceScriptCode:
                source_lang += "_" + request.config.language.sourceScriptCode
            # Removed automatic script code appending to match Triton model expectations
            
            if request.config.language.targetScriptCode:
                target_lang += "_" + request.config.language.targetScriptCode
            # Removed automatic script code appending to match Triton model expectations
            
            # Preprocess input texts
            input_texts = []
            for text_input in request.input:
                # Normalize text: replace newlines with spaces, strip whitespace
                normalized_text = text_input.source.replace("\n", " ").strip() if text_input.source else " "
                input_texts.append(normalized_text)
            
            # Create database request record
            total_text_length = sum(len(text) for text in input_texts)
            request_record = await self.repository.create_request(
                model_id=service_id,
                source_language=original_source_lang,
                target_language=original_target_lang,
                text_length=total_text_length,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            request_id = request_record.id
            
            # Batch processing (max 90 texts per batch)
            max_batch_size = 90
            output_batch = []
            
            for i in range(0, len(input_texts), max_batch_size):
                batch = input_texts[i:i + max_batch_size]
                
                try:
                    # Get appropriate Triton client for this service
                    triton_client = await self.get_triton_client(service_id, auth_headers)
                    
                    # Log the model name and endpoint for debugging
                    # Apply mapping: "indictrans" -> "nmt" for Triton server (in case model_name wasn't mapped earlier)
                    logger.info(f"DEBUG: model_name before mapping: '{model_name}' (type: {type(model_name)}, service_id: {service_id})")
                    if model_name == "indictrans" or (isinstance(model_name, str) and "indictrans" in model_name.lower()):
                        logger.info(f"Applying final mapping: '{model_name}' -> 'nmt' for Triton (service_id: {service_id})")
                        model_name = "nmt"
                    service_entry = await self._get_service_registry_entry(service_id, auth_headers)
                    endpoint = service_entry[0] if service_entry else "default"
                    logger.info(f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}")
                    
                    # Prepare Triton inputs
                    inputs, outputs = triton_client.get_translation_io_for_triton(
                        batch, source_lang, target_lang
                    )
                    
                    # CRITICAL FIX: Map "indictrans" to "nmt" for Triton server
                    # The Triton server has the model named "nmt", not "indictrans"
                    if model_name == "indictrans" or (isinstance(model_name, str) and "indictrans" in model_name.lower()):
                        logger.info(f"🔧 MAPPING: '{model_name}' -> 'nmt' for Triton (service_id: {service_id})")
                        model_name = "nmt"
                    
                    # Send Triton request
                    response = triton_client.send_triton_request(
                        model_name=model_name,
                        inputs=inputs,
                        outputs=outputs
                    )
                    
                    # Extract results
                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([])
                    
                    output_batch.extend(encoded_result.tolist())
                    
                except Exception as e:
                    logger.error(f"Triton inference failed for batch {i//max_batch_size}: {e}")
                    raise TritonInferenceError(f"Triton inference failed: {e}")
            
            # Format response
            results = []
            for source_text, result in zip(input_texts, output_batch):
                if isinstance(result, (list, tuple)) and len(result) > 0:
                    translated_text = result[0].decode("utf-8") if isinstance(result[0], bytes) else str(result[0])
                else:
                    translated_text = str(result) if result is not None else ""
                
                results.append(TranslationOutput(
                    source=source_text,
                    target=translated_text
                ))
            
            # Create response
            response = NMTInferenceResponse(output=results)
            
            # Database logging
            for result in results:
                await self.repository.create_result(
                    request_id=request_id,
                    translated_text=result.target,
                    source_text=result.source
                )
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                request_id=request_id,
                status="completed",
                processing_time=processing_time
            )
            
            logger.info(f"NMT inference completed for request {request_id} in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"NMT inference failed: {e}")
            
            # Update request status to failed
            if request_id:
                try:
                    await self.repository.update_request_status(
                        request_id=request_id,
                        status="failed",
                        error_message=str(e)
                    )
                except Exception as update_error:
                    logger.error(f"Failed to update request status: {update_error}")
            
            # Re-raise with appropriate error type
            if isinstance(e, TritonInferenceError):
                raise
            elif isinstance(e, TextProcessingError):
                raise
            else:
                raise TextProcessingError(f"NMT inference failed: {e}")
