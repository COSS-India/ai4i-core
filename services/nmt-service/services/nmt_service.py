"""
NMT Service
Main NMT service containing core inference logic
"""

import asyncio
import time
import json
import logging
from typing import Optional, List, Dict, Tuple
from uuid import UUID

import numpy as np
import httpx
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from models.nmt_request import NMTInferenceRequest
from models.nmt_response import NMTInferenceResponse, TranslationOutput
from repositories.nmt_repository import NMTRepository
from services.text_service import TextService
from utils.triton_client import TritonClient
from utils.model_management_client import ModelManagementClient, ServiceInfo
from utils.text_utils import count_words
from utils.pii_redact_client import (
    PII_SUPPORTED_LANG_CODES,
    pii_language_code,
    redact_for_storage,
)

try:
    from starlette.requests import Request
except ImportError:
    Request = None  # type: ignore

from ai4icore_constants.exceptions import (
    TritonInferenceError,
    TextProcessingError,
    ModelNotFoundError,
    ServiceUnavailableError
)

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("nmt-service")
from ai4icore_telemetry.standard_spans import StandardSpanManager

_standard_spans = StandardSpanManager("nmt")


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
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client = None,
        cache_ttl_seconds: int = 300,
        pii_redact_base_url: Optional[str] = None,
        pii_redact_timeout: float = 20.0,
        pii_http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.repository = repository
        self.text_service = text_service
        self.get_triton_client_func = get_triton_client_func
        self.model_management_client = model_management_client
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.pii_redact_base_url = (pii_redact_base_url or "").strip() or None
        self.pii_redact_timeout = pii_redact_timeout
        self.pii_http_client = pii_http_client
        self.cache_prefix = "nmt:triton"
        # Cache Triton clients and service metadata with TTL so we can refresh on endpoint move
        self._triton_clients: Dict[str, Tuple[TritonClient, str, float]] = {}
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}

    async def _persist_translation_results(
        self,
        request_id: UUID,
        results: List[TranslationOutput],
        original_source_lang: str,
        original_target_lang: str,
        auth_headers: Optional[Dict[str, str]],
        http_request: Optional[Request],
    ) -> List[Dict[str, str]]:
        """
        Write per-segment rows to the DB. When PII is configured and a side's language is
        supported (en, hi, mr, ta), that side is redacted before insert. API response text
        is unchanged — only stored rows are redacted.
        """
        tenant_id = None
        if http_request is not None:
            tenant_id = getattr(http_request.state, "tenant_id", None)
        tenant_header = str(tenant_id) if tenant_id else None

        src_lang = pii_language_code(original_source_lang)
        tgt_lang = pii_language_code(original_target_lang)
        src_ok = bool(src_lang) and src_lang in PII_SUPPORTED_LANG_CODES
        tgt_ok = bool(tgt_lang) and tgt_lang in PII_SUPPORTED_LANG_CODES

        stored_results: List[Dict[str, str]] = []

        if not self.pii_redact_base_url or (not src_ok and not tgt_ok):
            rows = []
            for result in results:
                rows.append(
                    {
                        "translated_text": result.target,
                        "source_text": result.source,
                    }
                )
                stored_results.append(
                    {
                        "source_text": result.source,
                        "translated_text": result.target,
                    }
                )
            if rows:
                await self.repository.create_results_bulk(
                    request_id=request_id,
                    rows=rows,
                )
            return stored_results

        async def maybe_redact(text: str, lang: str, supported: bool) -> str:
            if not supported or not text:
                return text
            try:
                return await redact_for_storage(
                    base_url=self.pii_redact_base_url,
                    text=text,
                    lang=lang,
                    auth_headers=auth_headers,
                    tenant_id=tenant_header,
                    timeout=self.pii_redact_timeout,
                    client=self.pii_http_client,
                )
            except Exception as exc:
                logger.warning(
                    "NMT: PII redact before DB storage failed; storing raw segment: %s",
                    exc,
                )
                return text

        rows = []
        for result in results:
            src_stored, tgt_stored = await asyncio.gather(
                maybe_redact(result.source, src_lang, src_ok),
                maybe_redact(result.target, tgt_lang, tgt_ok),
            )
            rows.append(
                {
                    "translated_text": tgt_stored,
                    "source_text": src_stored,
                }
            )
            stored_results.append(
                {
                    "source_text": src_stored,
                    "translated_text": tgt_stored,
                }
            )
        if rows:
            await self.repository.create_results_bulk(
                request_id=request_id,
                rows=rows,
            )
        return stored_results
    
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
                logger.error(
                    f"Failed to fetch service info for {service_id} from Model Management service: {e}"
                )
                # No fallback - Model Management is required
                raise TritonInferenceError(
                    f"Model Management service unavailable for service {service_id}: {e}. "
                    f"Please ensure the service is registered in Model Management database."
                )
        else:
            logger.error("Model Management client not available")
            raise TritonInferenceError(
                f"Model Management client not configured. Cannot resolve endpoint for service {service_id}. "
                f"Please ensure Model Management is properly configured."
            )
    
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
        """Get Triton client for the given service ID via Model Management (no fallback)"""
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
            logger.error(
                f"Error getting service registry entry for {service_id}: {e}"
            )
            raise TritonInferenceError(
                f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. "
                f"Error: {e}. Please ensure the service is registered in Model Management database."
            )
        
        # If we reach here, Model Management failed to resolve the endpoint
        raise TritonInferenceError(
            f"Model Management did not resolve serviceId: {service_id} and no default endpoint is allowed. "
            f"Please ensure the service is registered in Model Management database."
        )
    
    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        """Get Triton model name based on service ID from Model Management (no fallback)"""
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
                else:
                    raise TritonInferenceError(
                        f"Model Management returned 'unknown' model name for service {service_id}. "
                        f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
                    )
        except TritonInferenceError:
            raise
        except Exception as e:
            logger.error(f"Error getting model name for {service_id}: {e}")
            raise TritonInferenceError(
                f"Model Management did not resolve model name for serviceId: {service_id}. "
                f"Error: {e}. Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            )
        
        # If we reach here, Model Management failed to resolve the model name
        raise TritonInferenceError(
            f"Model Management did not resolve model name for serviceId: {service_id}. "
            f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
        )

    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str = None) -> Tuple[str, str]:
        """Extract normalized Triton endpoint and model name from service info"""
        endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
        model_name = service_info.triton_model

        # Try to infer model name from model inference endpoint metadata when provided
        if service_info.model_inference_endpoint:
            model_name = (
                service_info.model_inference_endpoint.get("model_name")
                or service_info.model_inference_endpoint.get("modelName")
                or service_info.model_inference_endpoint.get("model")
                or model_name    
            )
            
            # If not found at top level, check inside schema (common structure)
            if not model_name or model_name == "unknown":
                schema = service_info.model_inference_endpoint.get("schema", {})
                if isinstance(schema, dict):
                    model_name = (
                        schema.get("model_name")
                        or schema.get("modelName")
                        or schema.get("name")
                        or model_name
                    )

        # No fallback - Model Management must provide the model name
        if not model_name or model_name == "unknown":
            logger.error(
                f"Model Management did not provide model name for service {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            )
            model_name = "unknown"  # Will cause error downstream
        
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
        auth_headers: Optional[Dict[str, str]] = None,
        http_request: Optional[Request] = None,
    ) -> NMTInferenceResponse:
        """Run NMT inference. Uses request.state.service_id when set by middleware (e.g. A/B variant)."""
        if not tracer:
            return await self._run_inference_impl(
                request, user_id, api_key_id, session_id, auth_headers, http_request
            )
        
        start_time = time.time()
        request_id = None

        # Use middleware-resolved service_id when present (A/B variant); else from body
        service_id = (
            getattr(http_request.state, "service_id", None) if http_request else None
        ) or request.config.serviceId
        source_lang = request.config.language.sourceLanguage
        target_lang = request.config.language.targetLanguage

        # Store original languages for response + persistence
        original_source_lang = source_lang
        original_target_lang = target_lang

        # Handle script codes - only append if explicitly provided in request
        if request.config.language.sourceScriptCode:
            source_lang += "_" + request.config.language.sourceScriptCode
        if request.config.language.targetScriptCode:
            target_lang += "_" + request.config.language.targetScriptCode

        try:
            # Phase 2: preprocess
            with _standard_spans.preprocess() as preprocess_span:
                input_texts = []
                for text_input in request.input:
                    normalized_text = (
                        text_input.source.replace("\n", " ").strip()
                        if text_input.source
                        else " "
                    )
                    input_texts.append(normalized_text)
                total_text_length = sum(len(text) for text in input_texts)
                total_input_words = sum(count_words(text) for text in input_texts)
                preprocess_span.set_attribute("nmt.input.character_length", total_text_length)
                preprocess_span.set_attribute("nmt.input.word_count", total_input_words)
                preprocess_span.set_attribute("nmt.preprocessed_count", len(input_texts))

            # Phase 3: resolve_model (merge get_model_name + get_triton_client)
            with _standard_spans.resolve_model() as resolve_span:
                model_name = await self.get_model_name(service_id, auth_headers)
                resolve_span.set_attribute("nmt.model_name", model_name)

                triton_client = await self.get_triton_client(service_id, auth_headers)
                service_entry = await self._get_service_registry_entry(service_id, auth_headers)
                endpoint = service_entry[0] if service_entry else "default"
                resolve_span.set_attribute("nmt.triton_endpoint", endpoint)

                # Apply mapping: "indictrans" -> "nmt" for Triton server
                if model_name == "indictrans" or (
                    isinstance(model_name, str) and "indictrans" in model_name.lower()
                ):
                    logger.info(
                        f"🔧 MAPPING: '{model_name}' -> 'nmt' for Triton (service_id: {service_id})"
                    )
                    model_name = "nmt"

            # Phase 4: triton_inference (no span-per-loop-item; use events)
            max_batch_size = 90
            output_batch = []
            batch_count = (len(input_texts) + max_batch_size - 1) // max_batch_size

            with _standard_spans.triton_inference() as triton_span:
                triton_span.set_attribute("nmt.batch_count", batch_count)
                triton_span.set_attribute("nmt.max_batch_size", max_batch_size)

                for i in range(0, len(input_texts), max_batch_size):
                    batch = input_texts[i : i + max_batch_size]
                    batch_index = i // max_batch_size

                    triton_span.add_event(
                        "nmt.batch.started",
                        {"batch_index": batch_index, "batch_size": len(batch)},
                    )

                    # Prepare Triton inputs (event instead of span)
                    inputs, outputs = triton_client.get_translation_io_for_triton(
                        batch, source_lang, target_lang
                    )
                    triton_span.add_event(
                        "nmt.prepare_triton_inputs.completed",
                        {
                            "batch_index": batch_index,
                            "batch_size": len(batch),
                        },
                    )

                    # Send Triton request (triton_client will create its own span: triton.inference)
                    response = triton_client.send_triton_request(
                        model_name=model_name,
                        inputs=inputs,
                        outputs=outputs,
                    )

                    # Extract results (event instead of span)
                    encoded_result = response.as_numpy("OUTPUT_TEXT")
                    if encoded_result is None:
                        encoded_result = np.array([])

                    batch_results = encoded_result.tolist()
                    output_batch.extend(batch_results)
                    triton_span.add_event(
                        "nmt.extract_results.completed",
                        {
                            "batch_index": batch_index,
                            "result_count": len(batch_results),
                        },
                    )

                    triton_span.add_event(
                        "nmt.batch.completed",
                        {"batch_index": batch_index, "result_count": len(batch_results)},
                    )

            # Phase 5: postprocess
            with _standard_spans.postprocess() as post_span:
                results = []
                for source_text, result in zip(input_texts, output_batch):
                    if isinstance(result, (list, tuple)) and len(result) > 0:
                        translated_text = (
                            result[0].decode("utf-8")
                            if isinstance(result[0], bytes)
                            else str(result[0])
                        )
                    else:
                        translated_text = str(result) if result is not None else ""

                    results.append(
                        TranslationOutput(source=source_text, target=translated_text)
                    )

                output_texts = [result.target for result in results]
                total_output_characters = sum(len(text) for text in output_texts)
                total_output_words = sum(count_words(text) for text in output_texts)

                post_span.set_attribute("nmt.output.character_length", total_output_characters)
                post_span.set_attribute("nmt.output.word_count", total_output_words)
                post_span.set_attribute("nmt.formatted_count", len(results))

            response = NMTInferenceResponse(output=results)

            # Phase 6: persist (merge create_db_request + create_db_results + update_status)
            with _standard_spans.persist() as persist_span:
                request_record = await self.repository.create_request(
                    model_id=service_id,
                    source_language=original_source_lang,
                    target_language=original_target_lang,
                    text_length=total_text_length,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    session_id=session_id,
                )
                request_id = request_record.id
                persist_span.set_attribute("nmt.request_id", str(request_id))

                stored_results = await self._persist_translation_results(
                    request_id=request_id,
                    results=results,
                    original_source_lang=original_source_lang,
                    original_target_lang=original_target_lang,
                    auth_headers=auth_headers,
                    http_request=http_request,
                )
                persist_span.set_attribute("nmt.db_results_created", len(results))
                persist_span.set_attribute("nmt.db_results_redacted_count", len(stored_results))

                if http_request is not None:
                    http_request.state.persisted_translation_results = stored_results

                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    request_id=request_id,
                    status="completed",
                    processing_time=processing_time,
                )

            # Log output metrics for successful inference
            processing_time = time.time() - start_time
            logger.info(
                f"NMT inference completed for request {request_id} in {processing_time:.2f}s, "
                f"output_characters={total_output_characters}, output_words={total_output_words}",
                extra={
                    "input_details": {
                        "character_length": total_text_length,
                        "word_count": total_input_words,
                        "input_count": len(input_texts),
                    },
                    "output_details": {
                        "character_length": total_output_characters,
                        "word_count": total_output_words,
                        "output_count": len(response.output),
                    },
                    "request_id": str(request_id),
                    "processing_time_seconds": processing_time,
                    "service_id": service_id,
                    "source_language": original_source_lang,
                    "target_language": original_target_lang,
                },
            )
            return response

        except Exception as e:
            logger.error(f"NMT inference failed: {e}")

            # Update request status to failed (best effort)
            if request_id:
                try:
                    with _standard_spans.persist():
                        await self.repository.update_request_status(
                            request_id=request_id,
                            status="failed",
                            error_message=str(e),
                        )
                except Exception as update_error:
                    logger.error(f"Failed to update request status: {update_error}")

            if isinstance(e, TritonInferenceError):
                raise
            if isinstance(e, TextProcessingError):
                raise
            raise TextProcessingError(f"NMT inference failed: {e}")
    
    async def _run_inference_impl(
        self,
        request: NMTInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        http_request: Optional[Request] = None,
    ) -> NMTInferenceResponse:
        """Fallback when tracing is not available. Uses request.state.service_id when set by middleware."""
        start_time = time.time()
        request_id = None
        
        try:
            service_id = (
                getattr(http_request.state, "service_id", None) if http_request else None
            ) or request.config.serviceId
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
            
            if request.config.language.targetScriptCode:
                target_lang += "_" + request.config.language.targetScriptCode
            
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
                    
                    # Apply mapping: "indictrans" -> "nmt" for Triton server
                    if model_name == "indictrans" or (isinstance(model_name, str) and "indictrans" in model_name.lower()):
                        model_name = "nmt"
                    
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
            
            # Database logging (redacted per PII policy when configured + language supported)
            stored_results = await self._persist_translation_results(
                request_id=request_id,
                results=results,
                original_source_lang=original_source_lang,
                original_target_lang=original_target_lang,
                auth_headers=auth_headers,
                http_request=http_request,
            )
            if http_request is not None:
                http_request.state.persisted_translation_results = stored_results
            
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
