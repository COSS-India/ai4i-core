"""
NMT Service
Main NMT service containing core inference logic
"""

import time
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

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TextProcessingError(Exception):
    """Text processing error"""
    pass


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
        default_triton_client: TritonClient, 
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client = None
    ):
        self.repository = repository
        self.text_service = text_service
        self.default_triton_client = default_triton_client
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self._triton_clients = {}  # Cache for Triton clients
        self._service_registry_cache: Dict[str, Tuple[str, str]] = {}  # Cache for service registry
        self._service_info_cache: Dict[str, ServiceInfo] = {}  # Cache for service info
    
    async def _get_service_info(self, service_id: str) -> Optional[ServiceInfo]:
        """Get service info from model management service with caching"""
        # Check cache first
        if service_id in self._service_info_cache:
            return self._service_info_cache[service_id]
        
        # Fetch from model management service if client is available
        if self.model_management_client:
            try:
                service_info = await self.model_management_client.get_service(
                    service_id,
                    use_cache=True,
                    redis_client=self.redis_client
                )
                if service_info:
                    self._service_info_cache[service_id] = service_info
                    # Also update registry cache
                    if service_info.endpoint:
                        # Extract host:port from endpoint (remove http:// if present)
                        endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
                        model_name = service_info.triton_model or "nmt"
                        self._service_registry_cache[service_id] = (endpoint, model_name)
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
    
    async def _get_service_registry_entry(self, service_id: str) -> Optional[Tuple[str, str]]:
        """Get service registry entry (endpoint, model_name) for service_id"""
        # Check cache first
        if service_id in self._service_registry_cache:
            return self._service_registry_cache[service_id]
        
        # Fetch from model management service
        service_info = await self._get_service_info(service_id)
        if service_info and service_info.endpoint:
            # Extract host:port from endpoint (remove http:// if present)
            endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
            model_name = service_info.triton_model or "nmt"
            entry = (endpoint, model_name)
            self._service_registry_cache[service_id] = entry
            return entry
        
        return None
    
    async def get_triton_client(self, service_id: str) -> TritonClient:
        """Get Triton client for the given service ID with fallback to default"""
        # Check cache first
        if service_id in self._triton_clients:
            return self._triton_clients[service_id]
        
        # Get endpoint and model info from model management service
        try:
            service_entry = await self._get_service_registry_entry(service_id)
            if service_entry:
                endpoint, _ = service_entry
                # Create client using factory function if available
                if self.get_triton_client_func:
                    client = self.get_triton_client_func(endpoint)
                    self._triton_clients[service_id] = client
                    return client
        except Exception as e:
            logger.warning(
                f"Error getting service registry entry for {service_id}: {e}. "
                "Falling back to default Triton client."
            )
        
        # Fallback to default client if service not found or error occurred
        logger.debug(f"Using default Triton client for service {service_id}")
        return self.default_triton_client
    
    async def get_model_name(self, service_id: str) -> str:
        """Get Triton model name based on service ID with fallback"""
        try:
            service_entry = await self._get_service_registry_entry(service_id)
            if service_entry:
                return service_entry[1]  # Return model name
        except Exception as e:
            logger.debug(f"Error getting model name for {service_id}: {e}, using default 'nmt'")
        
        # Default to "nmt" if not found or error occurred
        return "nmt"
    
    async def run_inference(
        self,
        request: NMTInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
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
            model_name = await self.get_model_name(service_id)
            
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
                    triton_client = await self.get_triton_client(service_id)
                    
                    # Log the model name and endpoint for debugging
                    service_entry = await self._get_service_registry_entry(service_id)
                    endpoint = service_entry[0] if service_entry else "default"
                    logger.info(f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}")
                    
                    # Prepare Triton inputs
                    inputs, outputs = triton_client.get_translation_io_for_triton(
                        batch, source_lang, target_lang
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
