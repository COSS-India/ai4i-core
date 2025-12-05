"""
Transliteration Service
Main transliteration service containing core inference logic
"""

import time
import logging
from typing import Optional, List, Union
from uuid import UUID

import numpy as np

from models.transliteration_request import TransliterationInferenceRequest
from models.transliteration_response import TransliterationInferenceResponse, TransliterationOutput
from repositories.transliteration_repository import TransliterationRepository
from services.text_service import TextService
from utils.triton_client import TritonClient

logger = logging.getLogger(__name__)


class TritonInferenceError(Exception):
    """Triton inference error"""
    pass


class TextProcessingError(Exception):
    """Text processing error"""
    pass


class TransliterationService:
    """Main transliteration service for transliteration inference"""
    
    # Service registry mapping serviceId to (triton_endpoint, triton_model_name)
    # Each entry: service_id -> (endpoint, model_name)
    # Note: Triton HTTP client expects host:port format (without http://), and model names should not contain special characters
    SERVICE_REGISTRY = {
        "ai4bharat/indicxlit": ("65.1.35.3:8200", "transliteration"),
        "ai4bharat-transliteration": ("65.1.35.3:8200", "transliteration"),
        "indicxlit": ("65.1.35.3:8200", "transliteration"),
        "default": ("65.1.35.3:8200", "transliteration")
    }
    
    def __init__(
        self,
        repository: TransliterationRepository,
        text_service: TextService,
        default_triton_client: TritonClient,
        get_triton_client_func=None
    ):
        self.repository = repository
        self.text_service = text_service
        self.default_triton_client = default_triton_client
        self.get_triton_client_func = get_triton_client_func
        self._triton_clients = {}  # Cache for Triton clients
    
    def get_triton_client(self, service_id: str) -> TritonClient:
        """Get Triton client for the given service ID"""
        # Check cache first
        if service_id in self._triton_clients:
            return self._triton_clients[service_id]
        
        # Get endpoint and model info from registry
        service_info = self.SERVICE_REGISTRY.get(service_id)
        if service_info:
            endpoint, _ = service_info
        else:
            # Use default client if service not in registry
            return self.default_triton_client
        
        # Create client using factory function if available
        if self.get_triton_client_func:
            client = self.get_triton_client_func(endpoint)
            self._triton_clients[service_id] = client
            return client
        else:
            # Fallback to default client
            return self.default_triton_client
    
    def get_model_name(self, service_id: str) -> str:
        """Get Triton model name based on service ID"""
        service_info = self.SERVICE_REGISTRY.get(service_id)
        if service_info:
            return service_info[1]  # Return model name
        return "transliteration"  # Default to "transliteration" if not found
    
    async def run_inference(
        self,
        request: TransliterationInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None
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
            
            # Get model name dynamically based on service ID
            model_name = self.get_model_name(service_id)
            
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
                    # Get appropriate Triton client for this service
                    triton_client = self.get_triton_client(service_id)
                    
                    # Log the model name and endpoint for debugging
                    service_info = self.SERVICE_REGISTRY.get(service_id)
                    endpoint = service_info[0] if service_info else "default"
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

