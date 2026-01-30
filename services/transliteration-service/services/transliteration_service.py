"""
Transliteration Service
Main transliteration service containing core inference logic
"""

import time
import logging
from typing import Optional, List, Union, Dict, Tuple
from uuid import UUID
from contextlib import nullcontext

import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.transliteration_request import TransliterationInferenceRequest
from models.transliteration_response import TransliterationInferenceResponse, TransliterationOutput
from repositories.transliteration_repository import TransliterationRepository
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
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("transliteration-service")


class TransliterationService:
    """Main transliteration service for transliteration inference"""
    
    def __init__(
        self,
        repository: TransliterationRepository,
        text_service: TextService,
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client = None,
        cache_ttl_seconds: int = 300,
        default_triton_client: Optional[TritonClient] = None
    ):
        self.repository = repository
        self.text_service = text_service
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_prefix = "transliteration:triton"
        self.default_triton_client = default_triton_client
        # Cache Triton clients and service metadata with TTL so we can refresh on endpoint move
        self._triton_clients: Dict[str, Tuple[TritonClient, str, float]] = {}
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}
    
    def get_triton_client(self, service_id: str) -> TritonClient:
        """Get Triton client for the given service ID"""
        # If we already have a client cached for this service_id, reuse it
        if service_id in self._triton_clients:
            cached_client, cached_endpoint, cached_time = self._triton_clients[service_id]
            # Check if cache is still valid
            if time.time() - cached_time < self.cache_ttl_seconds:
                return cached_client

        # Use default_triton_client if available (set by middleware)
        if self.default_triton_client:
            endpoint = getattr(self.default_triton_client, "triton_url", None)
            if endpoint:
                # Cache and return the default client
                self._triton_clients[service_id] = (self.default_triton_client, endpoint, time.time())
                return self.default_triton_client

        # If no default client, we need to get service info from Model Management
        # This shouldn't normally happen as middleware should set it, but fallback logic
        if not self.model_management_client:
            raise TritonInferenceError(
                "No Triton endpoint available. Model Management client not configured."
            )

        # This is a fallback - normally middleware should have already resolved this
        raise TritonInferenceError(
            f"No Triton endpoint available for service {service_id}. "
            "Ensure Model Management middleware resolved the endpoint correctly."
        )
    
    def get_model_name(self, service_id: str) -> str:
        """
        Get Triton model name based on service ID.
        
        Currently we use a single Triton model named "transliteration" for all
        transliteration services. If in the future Model Management exposes
        different model names per service, this function can be extended to
        derive the model name from that metadata instead of hardcoding it here.
        """
        return "transliteration"
    
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
            
            # Get model name dynamically based on service ID
            model_name = self.get_model_name(service_id)
            
            # Validate top_k for sentence level
            if top_k > 0 and is_sentence:
                raise ValueError("numSuggestions (top_k) is not valid for sentence level transliteration")
            
            # Preprocess input texts with tracing
            if tracer:
                preprocess_span_context = tracer.start_as_current_span("transliteration.preprocess_inputs")
            else:
                preprocess_span_context = nullcontext()
            
            with preprocess_span_context as preprocess_span:
                input_texts = []
                for text_input in request.input:
                    # Normalize text: replace newlines with spaces, strip whitespace
                    normalized_text = text_input.source.replace("\n", " ").strip() if text_input.source else ""
                    input_texts.append(normalized_text)
                
                if preprocess_span:
                    preprocess_span.set_attribute("transliteration.input_count", len(input_texts))
                    preprocess_span.set_attribute("transliteration.total_chars", sum(len(text) for text in input_texts))
            
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
            
            # Create span for batch processing
            if tracer:
                batch_loop_span_context = tracer.start_as_current_span("transliteration.batch_processing")
            else:
                batch_loop_span_context = nullcontext()
            
            with batch_loop_span_context as batch_loop_span:
                if batch_loop_span:
                    batch_loop_span.set_attribute("transliteration.batch_size", max_batch_size)
                    batch_loop_span.set_attribute("transliteration.total_batches", (len(input_texts) + max_batch_size - 1) // max_batch_size)
                
                for i in range(0, len(input_texts), max_batch_size):
                    batch = input_texts[i:i + max_batch_size]
                    
                    try:
                        # Get appropriate Triton client for this service
                        triton_client = self.get_triton_client(service_id)
                        
                        # Log the model name and endpoint for debugging
                        endpoint = getattr(triton_client, "triton_url", "unknown")
                        logger.info(
                            f"Using Triton endpoint: {endpoint}, model: {model_name} for service: {service_id}"
                        )
                        
                        # Prepare Triton inputs with tracing
                        if tracer:
                            prepare_span_context = tracer.start_as_current_span("transliteration.prepare_triton_inputs")
                        else:
                            prepare_span_context = nullcontext()
                        
                        with prepare_span_context as prepare_span:
                            inputs, outputs = triton_client.get_transliteration_io_for_triton(
                                batch, source_lang, target_lang, not is_sentence, top_k
                            )
                            if prepare_span:
                                prepare_span.set_attribute("transliteration.batch_index", i // max_batch_size + 1)
                                prepare_span.set_attribute("transliteration.batch_text_count", len(batch))
                                prepare_span.set_attribute("transliteration.input_count", len(inputs))
                                prepare_span.set_attribute("transliteration.output_count", len(outputs))
                                prepare_span.set_attribute("transliteration.source_lang", source_lang)
                                prepare_span.set_attribute("transliteration.target_lang", target_lang)
                        
                        # Send Triton request (this will create its own triton.inference span)
                        response = triton_client.send_triton_request(
                            model_name=model_name,
                            inputs=inputs,
                            outputs=outputs
                        )
                        
                        # Extract results with tracing
                        if tracer:
                            extract_span_context = tracer.start_as_current_span("transliteration.extract_results")
                        else:
                            extract_span_context = nullcontext()
                        
                        with extract_span_context as extract_span:
                            encoded_result = response.as_numpy("OUTPUT_TEXT")
                            if encoded_result is None:
                                encoded_result = np.array([np.array([])])
                            
                            # Decode results
                            batch_results = []
                            for result_row in encoded_result:
                                if isinstance(result_row, np.ndarray):
                                    # Multiple suggestions (word-level with top_k)
                                    decoded_results = [r.decode("utf-8") if isinstance(r, bytes) else str(r) for r in result_row]
                                    batch_results.append(decoded_results)
                                else:
                                    # Single result (sentence-level or word-level without top_k)
                                    decoded_result = result_row.decode("utf-8") if isinstance(result_row, bytes) else str(result_row)
                                    batch_results.append([decoded_result])
                            
                            output_batch.extend(batch_results)
                            
                            if extract_span:
                                extract_span.set_attribute("transliteration.result_count", len(batch_results))
                        
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

