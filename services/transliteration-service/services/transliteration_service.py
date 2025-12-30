"""
Transliteration Service
Main transliteration service containing core inference logic
"""

import time
import logging
from typing import Optional, List, Union, Dict, Tuple
from uuid import UUID

import numpy as np

from models.transliteration_request import TransliterationInferenceRequest
from models.transliteration_response import TransliterationInferenceResponse, TransliterationOutput
from repositories.transliteration_repository import TransliterationRepository
from services.text_service import TextService
from utils.triton_client import TritonClient
from ai4icore_model_management import ModelManagementClient, ServiceInfo

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TextProcessingError(Exception):
    """Text processing error"""
    pass


class TransliterationService:
    """Main transliteration service for transliteration inference"""
    
    def __init__(
        self,
        repository: TransliterationRepository,
        text_service: TextService,
        get_triton_client_func,
        model_management_client: ModelManagementClient,
        redis_client = None,
        cache_ttl_seconds: int = 300
    ):
        """
        Initialize TransliterationService
        
        Args:
            repository: Database repository for transliteration operations
            text_service: Text processing service
            get_triton_client_func: Factory function to create Triton clients
            model_management_client: Client for model management service (REQUIRED)
            redis_client: Optional Redis client for distributed caching
            cache_ttl_seconds: Cache TTL in seconds
        
        Raises:
            ValueError: If model_management_client is None
        """
        if model_management_client is None:
            raise ValueError("model_management_client is required. Model management service must be available.")
        
        self.repository = repository
        self.text_service = text_service
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self._triton_clients = {}  # Cache for Triton clients
        
        # Service info cache (service_id -> (ServiceInfo, expires_at))
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
        
        # Service registry cache (service_id -> (endpoint, model_name, expires_at))
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
    
    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> ServiceInfo:
        """
        Get service info from model management service with caching
        
        Args:
            service_id: Service ID to fetch
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            ServiceInfo object
            
        Raises:
            ValueError: If service not found or model management service error
        """
        # Check cache first
        cached = self._service_info_cache.get(service_id)
        if cached:
            service_info, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service info cache hit for {service_id}")
                return service_info
            # Expired entry
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
                error_msg = f"Service '{service_id}' not found in model management service. Please register the service first."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Validate service info has required fields
            if not service_info.endpoint:
                error_msg = f"Service '{service_id}' has no endpoint configured in model management service"
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
            
        except Exception as e:
            error_msg = f"Failed to fetch service info for {service_id} from model management service: {e}"
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    
    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str) -> Tuple[str, str]:
        """
        Extract Triton endpoint and model name from ServiceInfo
        
        Args:
            service_info: ServiceInfo from model management service
            service_id: Service ID for logging
            
        Returns:
            Tuple of (endpoint, model_name)
        """
        # Extract endpoint (remove http:// or https:// prefix if present)
        endpoint = service_info.endpoint or ""
        endpoint = endpoint.replace("http://", "").replace("https://", "").strip()
        
        # Extract model name - try multiple sources
        model_name = service_info.triton_model or "transliteration"
        
        # Check model_inference_endpoint for model name
        if service_info.model_inference_endpoint:
            if isinstance(service_info.model_inference_endpoint, dict):
                endpoint_model_name = service_info.model_inference_endpoint.get("modelName")
                if endpoint_model_name:
                    model_name = endpoint_model_name
        
        logger.info(f"Extracted Triton metadata for {service_id}: endpoint={endpoint}, model_name={model_name}")
        return endpoint, model_name
    
    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
        """
        Get service registry entry (endpoint, model_name) for the given service ID
        
        Tries in order:
        1. Service registry cache
        2. Model management service (REQUIRED)
        
        Args:
            service_id: Service ID to fetch
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            Tuple of (endpoint, model_name)
            
        Raises:
            ValueError: If service not found or error fetching from model management
        """
        # Check registry cache first
        cached = self._service_registry_cache.get(service_id)
        if cached:
            endpoint, model_name, expires_at = cached
            if expires_at > time.time():
                logger.debug(f"Service registry cache hit for {service_id}")
                return (endpoint, model_name)
            # Expired entry
            self._service_registry_cache.pop(service_id, None)
        
        # Get from model management service (REQUIRED - will raise ValueError if not found)
        service_info = await self._get_service_info(service_id, auth_headers)
        endpoint, model_name = self._extract_triton_metadata(service_info, service_id)
        return (endpoint, model_name)
    
    async def get_triton_client(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> TritonClient:
        """
        Get Triton client for the given service ID
        
        Args:
            service_id: Service ID to get client for
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            TritonClient configured for the service endpoint
            
        Raises:
            ValueError: If service not found or endpoint not configured
        """
        # Check cache first
        if service_id in self._triton_clients:
            logger.debug(f"Triton client cache hit for {service_id}")
            return self._triton_clients[service_id]
        
        # Get endpoint and model info from model management service (REQUIRED)
        endpoint, _ = await self._get_service_registry_entry(service_id, auth_headers)
        
        # Create client using factory function
        logger.info(f"Creating Triton client for service {service_id} with endpoint {endpoint}")
        client = self.get_triton_client_func(endpoint)
        self._triton_clients[service_id] = client
        return client
    
    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        """
        Get Triton model name based on service ID
        
        Args:
            service_id: Service ID to get model name for
            auth_headers: Optional auth headers from incoming request
            
        Returns:
            Triton model name
            
        Raises:
            ValueError: If service not found
        """
        _, model_name = await self._get_service_registry_entry(service_id, auth_headers)
        return model_name
    
    async def run_inference(
        self,
        request: TransliterationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None
    ) -> TransliterationInferenceResponse:
        """Run transliteration inference on the given request"""
        start_time = time.time()
        request_id = None
        
        try:
            # Extract configuration
            service_id = request.config.serviceId
            source_lang = request.config.language.sourceLanguage
            target_lang = request.config.language.targetLanguage
            is_sentence = request.config.isSentence
            top_k = request.config.numSuggestions
            
            # Get model name dynamically based on service ID (from model management service)
            model_name = await self.get_model_name(service_id, auth_headers)
            
            # Validate top_k for sentence level
            if top_k > 0 and is_sentence:
                raise ValueError("numSuggestions (top_k) is not valid for sentence level transliteration")
            
            # Preprocess input texts
            input_texts = []
            for text_input in request.input:
                # Normalize text: replace newlines with spaces, strip whitespace
                normalized_text = text_input.source.replace("\n", " ").strip() if text_input.source else ""
                input_texts.append(normalized_text)
            
            # Create database request record
            total_text_length = sum(len(text) for text in input_texts)
            request_record = await self.repository.create_request(
                model_id=service_id,
                source_language=source_lang,
                target_language=target_lang,
                text_length=total_text_length,
                is_sentence_level=is_sentence,
                num_suggestions=top_k,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            request_id = request_record.id
            
            # Batch processing (max 100 texts per batch)
            max_batch_size = 100
            output_batch = []
            
            for i in range(0, len(input_texts), max_batch_size):
                batch = input_texts[i:i + max_batch_size]
                
                try:
                    # Get appropriate Triton client for this service (from model management service)
                    triton_client = await self.get_triton_client(service_id, auth_headers)
                    
                    # Log the model name and endpoint for debugging
                    registry_entry = await self._get_service_registry_entry(service_id, auth_headers)
                    endpoint = registry_entry[0] if registry_entry else "default"
                    logger.info(f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}")
                    
                    # Prepare Triton inputs
                    inputs, outputs = triton_client.get_transliteration_io_for_triton(
                        batch, source_lang, target_lang, not is_sentence, top_k
                    )
                    
                    # Send Triton request
                    response = triton_client.send_triton_request(
                        model_name=model_name,
                        inputs=inputs,
                        outputs=outputs
                    )
                    
                    # Extract results
                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([np.array([])])
                    
                    # Decode results
                    for result_row in encoded_result:
                        if isinstance(result_row, np.ndarray):
                            # Multiple suggestions (word-level with top_k)
                            decoded_results = [r.decode("utf-8") if isinstance(r, bytes) else str(r) for r in result_row]
                            output_batch.append(decoded_results)
                        else:
                            # Single result (sentence-level or word-level without top_k)
                            decoded_result = result_row.decode("utf-8") if isinstance(result_row, bytes) else str(result_row)
                            output_batch.append([decoded_result])
                    
                except Exception as e:
                    logger.error(f"Triton inference failed for batch {i//max_batch_size}: {e}")
                    raise TritonInferenceError(f"Triton inference failed: {e}")
            
            # Format response
            results = []
            for source_text, result_list in zip(input_texts, output_batch):
                if not source_text:
                    # Empty input returns empty output
                    transliterated = source_text
                elif len(result_list) == 1:
                    # Single result - return as string
                    transliterated = result_list[0] if result_list else source_text
                else:
                    # Multiple results - return as list
                    transliterated = result_list if result_list else [source_text]
                
                results.append(TransliterationOutput(
                    source=source_text,
                    target=transliterated
                ))
            
            # Create response
            response = TransliterationInferenceResponse(output=results)
            
            # Database logging
            for result in results:
                await self.repository.create_result(
                    request_id=request_id,
                    transliterated_text=result.target,
                    source_text=result.source
                )
            
            # Update request status
            processing_time = time.time() - start_time
            await self.repository.update_request_status(
                request_id=request_id,
                status="completed",
                processing_time=processing_time
            )
            
            logger.info(f"Transliteration inference completed for request {request_id} in {processing_time:.2f}s")
            return response
            
        except Exception as e:
            logger.error(f"Transliteration inference failed: {e}")
            
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
                raise TextProcessingError(f"Transliteration inference failed: {e}")

