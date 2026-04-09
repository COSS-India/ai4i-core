"""
NMT Service
Main NMT service containing core inference logic.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import httpx
import numpy as np
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.schemas.inference import NMTInferenceRequest, NMTInferenceResponse, TranslationOutput
from app.repositories.nmt_repository import NMTRepository
from app.clients.triton_client import NMTTritonClient
from app.clients.model_management_client import ModelManagementClient, ServiceInfo
from app.clients.pii_client import PII_SUPPORTED_LANG_CODES, pii_language_code, redact_for_storage

try:
    from starlette.requests import Request
except ImportError:
    Request = None  # type: ignore

from ai4icore_exceptions import (
    TritonInferenceError,
    TextProcessingError,
    ModelNotFoundError,
    ServiceUnavailableError,
)
from ai4icore_telemetry import StandardSpanManager

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("nmt-service")
_standard_spans = StandardSpanManager("nmt")


def _count_words(text: str) -> int:
    """Count words in text (whitespace-split)."""
    try:
        return len(text.split()) if text else 0
    except Exception:
        return 0


class NMTService:
    """Main NMT service for translation inference."""

    LANG_CODE_TO_SCRIPT_CODE = {
        "hi": "Deva", "ur": "Arab", "ta": "Taml", "te": "Telu",
        "kn": "Knda", "ml": "Mlym", "bn": "Beng", "gu": "Gujr",
        "mr": "Deva", "pa": "Guru", "or": "Orya", "as": "Beng",
    }

    def __init__(
        self,
        repository: NMTRepository,
        text_service=None,
        get_triton_client_func=None,
        model_management_client: Optional[ModelManagementClient] = None,
        redis_client=None,
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
        self._triton_clients: Dict[str, Tuple[NMTTritonClient, str, float]] = {}
        self._service_registry_cache: Dict[str, Tuple[str, str, float]] = {}
        self._service_info_cache: Dict[str, Tuple[ServiceInfo, float]] = {}

    # ──────────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────────

    async def run_inference(
        self,
        request: NMTInferenceRequest,
        user_id: Optional[int] = None,
        api_key_id: Optional[int] = None,
        session_id: Optional[int] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        http_request: Optional[Request] = None,
    ) -> NMTInferenceResponse:
        """Run NMT inference with StandardSpanManager phases and fallback retry."""
        start_time = time.time()
        request_id = None

        try:
            service_id = (
                getattr(http_request.state, "service_id", None) if http_request else None
            ) or request.config.serviceId
            source_lang = request.config.language.sourceLanguage
            target_lang = request.config.language.targetLanguage

            original_source_lang = source_lang
            original_target_lang = target_lang

            if request.config.language.sourceScriptCode:
                source_lang += "_" + request.config.language.sourceScriptCode
            if request.config.language.targetScriptCode:
                target_lang += "_" + request.config.language.targetScriptCode

            with _standard_spans.preprocess() as preprocess_span:
                input_texts = [
                    (ti.source.replace("\n", " ").strip() if ti.source else " ")
                    for ti in request.input
                ]
                total_text_length = sum(len(t) for t in input_texts)
                total_input_words = sum(_count_words(t) for t in input_texts)
                preprocess_span.set_attribute(
                    "nmt.input.character_length", total_text_length
                )
                preprocess_span.set_attribute("nmt.input.word_count", total_input_words)
                preprocess_span.set_attribute("nmt.preprocessed_count", len(input_texts))

            with _standard_spans.resolve_model() as resolve_span:
                model_name = await self.get_model_name(service_id, auth_headers)
                resolve_span.set_attribute("nmt.model_name", model_name)

                triton_client = await self.get_triton_client(service_id, auth_headers)
                service_entry = await self._get_service_registry_entry(
                    service_id, auth_headers
                )
                endpoint = service_entry[0] if service_entry else ""
                resolve_span.set_attribute("nmt.triton_endpoint", endpoint)

                effective_model = model_name
                if effective_model and "indictrans" in effective_model.lower():
                    effective_model = "nmt"

            with tracer.start_as_current_span("nmt.create_db_request"):
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

            max_batch_size = 90
            output_batch: list = []
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
                    try:
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
                        response = triton_client.send_triton_request(
                            model_name=effective_model,
                            inputs=inputs,
                            outputs=outputs,
                        )
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
                            {
                                "batch_index": batch_index,
                                "result_count": len(batch_results),
                            },
                        )
                    except Exception as e:
                        triton_span.set_status(Status(StatusCode.ERROR, str(e)))
                        triton_span.record_exception(e)
                        raise TritonInferenceError(f"Triton inference failed: {e}")

            with _standard_spans.postprocess() as post_span:
                results = self._format_results(input_texts, output_batch)
                total_output_characters = sum(len(r.target) for r in results)
                total_output_words = sum(_count_words(r.target) for r in results)
                post_span.set_attribute(
                    "nmt.output.character_length", total_output_characters
                )
                post_span.set_attribute("nmt.output.word_count", total_output_words)
                post_span.set_attribute("nmt.formatted_count", len(results))

            nmt_response = NMTInferenceResponse(output=results)

            with _standard_spans.persist() as persist_span:
                persist_span.set_attribute("nmt.request_id", str(request_id))
                stored = await self._persist_translation_results(
                    request_id=request_id,
                    results=results,
                    original_source_lang=original_source_lang,
                    original_target_lang=original_target_lang,
                    auth_headers=auth_headers,
                    http_request=http_request,
                )
                persist_span.set_attribute("nmt.db_results_created", len(results))
                persist_span.set_attribute(
                    "nmt.db_results_redacted_count", len(stored)
                )
                if http_request is not None:
                    http_request.state.persisted_translation_results = stored

                processing_time = time.time() - start_time
                await self.repository.update_request_status(
                    request_id=request_id,
                    status="completed",
                    processing_time=processing_time,
                )

            processing_time = time.time() - start_time
            logger.info(
                "NMT inference completed",
                extra={
                    "request_id": str(request_id),
                    "processing_time_seconds": processing_time,
                    "service_id": service_id,
                    "input_details": {
                        "character_length": total_text_length,
                        "word_count": total_input_words,
                    },
                    "output_details": {
                        "character_length": total_output_characters,
                        "word_count": total_output_words,
                    },
                },
            )
            return nmt_response

        except (TritonInferenceError, ModelNotFoundError, ServiceUnavailableError) as exc:
            fallback_service_id = (
                getattr(http_request.state, "fallback_service_id", None)
                if http_request
                else None
            )
            original_service_id = request.config.serviceId

            if fallback_service_id and fallback_service_id != original_service_id:
                logger.warning(
                    "NMT: Primary service failed, attempting fallback",
                    extra={
                        "primary_service_id": original_service_id,
                        "fallback_service_id": fallback_service_id,
                        "error": str(exc),
                    },
                )
                try:
                    from app.services.smr_service import SMRService

                    smr_svc = SMRService()
                    triton_endpoint, triton_api_key, triton_model_name = (
                        await smr_svc.switch_to_fallback(
                            request, http_request, fallback_service_id
                        )
                    )
                    fallback_nmt = self._build_fallback_service(
                        http_request,
                        fallback_service_id,
                        triton_endpoint,
                        triton_api_key,
                        triton_model_name,
                    )
                    return await fallback_nmt.run_inference(
                        request=request,
                        user_id=user_id,
                        api_key_id=api_key_id,
                        session_id=session_id,
                        auth_headers=auth_headers,
                        http_request=http_request,
                    )
                except Exception as fallback_err:
                    combined = (
                        f"Primary service ({original_service_id}) failed: {exc}. "
                        f"Fallback service ({fallback_service_id}) also failed: {fallback_err}"
                    )
                    raise TritonInferenceError(combined) from fallback_err

            self._mark_failed(request_id, str(exc))
            raise

        except Exception as exc:
            span = trace.get_current_span()
            if span.is_recording():
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
            self._mark_failed(request_id, str(exc))
            if isinstance(exc, TextProcessingError):
                raise
            raise TextProcessingError(f"NMT inference failed: {exc}")

    # ──────────────────────────────────────────────
    # Triton client / model resolution (cached)
    # ──────────────────────────────────────────────

    async def _get_service_info(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[ServiceInfo]:
        cached = self._service_info_cache.get(service_id)
        if cached:
            info, expires = cached
            if expires > time.time():
                return info
            self._service_info_cache.pop(service_id, None)

        if self.model_management_client:
            try:
                info = await self.model_management_client.get_service(
                    service_id, use_cache=True, redis_client=self.redis_client, auth_headers=auth_headers,
                )
                if info:
                    expires = time.time() + self.cache_ttl_seconds
                    self._service_info_cache[service_id] = (info, expires)
                    if info.endpoint:
                        ep, mn = self._extract_triton_metadata(info, service_id)
                        self._service_registry_cache[service_id] = (ep, mn, expires)
                return info
            except Exception as e:
                raise TritonInferenceError(f"Model Management service unavailable for service {service_id}: {e}")
        raise TritonInferenceError(f"Model Management client not configured for service {service_id}")

    async def _get_service_registry_entry(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> Optional[Tuple[str, str]]:
        cached = self._service_registry_cache.get(service_id)
        if cached:
            ep, mn, expires = cached
            if expires > time.time():
                if mn == "indictrans":
                    mn = "nmt"
                return ep, mn
            self._service_registry_cache.pop(service_id, None)

        redis_entry = await self._get_registry_from_redis(service_id)
        if redis_entry:
            ep, mn = redis_entry
            if mn == "indictrans":
                mn = "nmt"
            expires = time.time() + self.cache_ttl_seconds
            self._service_registry_cache[service_id] = (ep, mn, expires)
            return ep, mn

        info = await self._get_service_info(service_id, auth_headers)
        if info and info.endpoint:
            ep, mn = self._extract_triton_metadata(info, service_id)
            expires = time.time() + self.cache_ttl_seconds
            self._service_registry_cache[service_id] = (ep, mn, expires)
            await self._set_registry_in_redis(service_id, ep, mn)
            return ep, mn
        return None

    async def get_triton_client(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> NMTTritonClient:
        cached = self._triton_clients.get(service_id)
        if cached:
            client, endpoint, expires = cached
            if expires > time.time():
                entry = await self._get_service_registry_entry(service_id, auth_headers)
                if entry and entry[0] != endpoint:
                    self._triton_clients.pop(service_id, None)
                else:
                    return client
            else:
                self._triton_clients.pop(service_id, None)

        entry = await self._get_service_registry_entry(service_id, auth_headers)
        if entry:
            ep, _ = entry
            if self.get_triton_client_func:
                client = self.get_triton_client_func(ep)
                self._triton_clients[service_id] = (client, ep, time.time() + self.cache_ttl_seconds)
                return client

        raise TritonInferenceError(
            f"Model Management did not resolve serviceId: {service_id}. "
            "Please ensure the service is registered in Model Management database."
        )

    async def get_model_name(self, service_id: str, auth_headers: Optional[Dict[str, str]] = None) -> str:
        entry = await self._get_service_registry_entry(service_id, auth_headers)
        if entry:
            mn = entry[1]
            if mn and mn != "unknown":
                return "nmt" if mn == "indictrans" else mn
            raise TritonInferenceError(
                f"Model Management returned 'unknown' model name for service {service_id}."
            )
        raise TritonInferenceError(
            f"Model Management did not resolve model name for serviceId: {service_id}."
        )

    # ──────────────────────────────────────────────
    # Cache helpers
    # ──────────────────────────────────────────────

    def _extract_triton_metadata(self, service_info: ServiceInfo, service_id: str = None) -> Tuple[str, str]:
        endpoint = service_info.endpoint.replace("http://", "").replace("https://", "")
        model_name = service_info.triton_model

        if service_info.model_inference_endpoint:
            ie = service_info.model_inference_endpoint
            if isinstance(ie, dict):
                model_name = (
                    ie.get("model_name") or ie.get("modelName") or ie.get("model") or model_name
                )
                if not model_name or model_name == "unknown":
                    schema = ie.get("schema", {})
                    if isinstance(schema, dict):
                        model_name = schema.get("model_name") or schema.get("modelName") or schema.get("name") or model_name

        if not model_name or model_name == "unknown":
            logger.error("Model Management did not provide model name for service %s", service_id)
            model_name = "unknown"

        return endpoint, model_name

    async def _get_registry_from_redis(self, service_id: str) -> Optional[Tuple[str, str]]:
        if not self.redis_client:
            return None
        try:
            cached = await self.redis_client.get(f"{self.cache_prefix}:registry:{service_id}")
            if cached:
                data = json.loads(cached)
                ep, mn = data.get("endpoint"), data.get("model_name")
                if ep and mn:
                    return ep, mn
        except Exception as e:
            logger.warning("Redis read failed for service %s: %s", service_id, e)
        return None

    async def _set_registry_in_redis(self, service_id: str, endpoint: str, model_name: str):
        if not self.redis_client:
            return
        try:
            payload = json.dumps({"endpoint": endpoint, "model_name": model_name})
            await self.redis_client.setex(f"{self.cache_prefix}:registry:{service_id}", self.cache_ttl_seconds, payload)
        except Exception as e:
            logger.warning("Redis write failed for service %s: %s", service_id, e)

    async def invalidate_cache(self, service_id: str):
        self._service_info_cache.pop(service_id, None)
        self._service_registry_cache.pop(service_id, None)
        self._triton_clients.pop(service_id, None)
        if self.redis_client:
            try:
                await self.redis_client.delete(f"{self.cache_prefix}:registry:{service_id}")
                await self.redis_client.delete(f"model_mgmt:service:{service_id}")
            except Exception as e:
                logger.warning("Failed to invalidate Redis cache for %s: %s", service_id, e)

    # ──────────────────────────────────────────────
    # PII-aware persistence
    # ──────────────────────────────────────────────

    async def _persist_translation_results(
        self,
        request_id: UUID,
        results: List[TranslationOutput],
        original_source_lang: str,
        original_target_lang: str,
        auth_headers: Optional[Dict[str, str]],
        http_request: Optional[Request],
    ) -> List[Dict[str, str]]:
        tenant_id = getattr(http_request.state, "tenant_id", None) if http_request else None
        tenant_header = str(tenant_id) if tenant_id else None

        src_lang = pii_language_code(original_source_lang)
        tgt_lang = pii_language_code(original_target_lang)
        src_ok = bool(src_lang) and src_lang in PII_SUPPORTED_LANG_CODES
        tgt_ok = bool(tgt_lang) and tgt_lang in PII_SUPPORTED_LANG_CODES

        stored_results: List[Dict[str, str]] = []

        if not self.pii_redact_base_url or (not src_ok and not tgt_ok):
            rows = []
            for r in results:
                rows.append({"translated_text": r.target, "source_text": r.source})
                stored_results.append({"source_text": r.source, "translated_text": r.target})
            if rows:
                await self.repository.create_results_bulk(request_id=request_id, rows=rows)
            return stored_results

        async def _maybe_redact(text: str, lang: str, supported: bool) -> str:
            if not supported or not text:
                return text
            try:
                return await redact_for_storage(
                    base_url=self.pii_redact_base_url,
                    text=text, lang=lang,
                    auth_headers=auth_headers, tenant_id=tenant_header,
                    timeout=self.pii_redact_timeout, client=self.pii_http_client,
                )
            except Exception as exc:
                logger.warning("PII redact failed; storing raw: %s", exc)
                return text

        rows = []
        for r in results:
            src_stored, tgt_stored = await asyncio.gather(
                _maybe_redact(r.source, src_lang, src_ok),
                _maybe_redact(r.target, tgt_lang, tgt_ok),
            )
            rows.append({"translated_text": tgt_stored, "source_text": src_stored})
            stored_results.append({"source_text": src_stored, "translated_text": tgt_stored})
        if rows:
            await self.repository.create_results_bulk(request_id=request_id, rows=rows)
        return stored_results

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _format_results(input_texts: List[str], output_batch: list) -> List[TranslationOutput]:
        results = []
        for src, raw in zip(input_texts, output_batch):
            if isinstance(raw, (list, tuple)) and len(raw) > 0:
                translated = raw[0].decode("utf-8") if isinstance(raw[0], bytes) else str(raw[0])
            else:
                translated = str(raw) if raw is not None else ""
            results.append(TranslationOutput(source=src, target=translated))
        return results

    def _build_fallback_service(
        self,
        http_request: Request,
        fallback_service_id: str,
        triton_endpoint: str,
        triton_api_key: str,
        triton_model_name: str,
    ) -> "NMTService":
        """Build a new NMTService pre-populated with fallback endpoint caches."""
        from app.services.text_service import TextService

        def _client_factory(endpoint: str) -> NMTTritonClient:
            url = endpoint
            if url.startswith(("http://", "https://")):
                url = url.split("://", 1)[1]
            return NMTTritonClient(triton_url=url, api_key=triton_api_key)

        mm_client = getattr(http_request.app.state, "model_management_client", None)
        redis = getattr(http_request.app.state, "redis_client", None)
        cache_ttl = getattr(mm_client, "cache_ttl_seconds", 300) if mm_client else 300

        fb = NMTService(
            repository=self.repository,
            text_service=TextService(),
            get_triton_client_func=_client_factory,
            model_management_client=mm_client,
            redis_client=redis,
            cache_ttl_seconds=cache_ttl,
            pii_redact_base_url=self.pii_redact_base_url,
            pii_redact_timeout=self.pii_redact_timeout,
            pii_http_client=self.pii_http_client,
        )

        expires = time.time() + cache_ttl
        fb._triton_clients[fallback_service_id] = (_client_factory(triton_endpoint), triton_endpoint, expires)
        fb._service_registry_cache[fallback_service_id] = (triton_endpoint, triton_model_name, expires)
        fb_info = ServiceInfo(
            service_id=fallback_service_id, model_id="",
            endpoint=triton_endpoint, api_key=triton_api_key,
            triton_model=triton_model_name, model_name=triton_model_name,
        )
        fb._service_info_cache[fallback_service_id] = (fb_info, expires)
        return fb

    def _mark_failed(self, request_id, error_message: str):
        """Best-effort mark request as failed (fire-and-forget in background)."""
        if not request_id:
            return
        try:
            asyncio.get_event_loop().create_task(
                self.repository.update_request_status(request_id=request_id, status="failed", error_message=error_message)
            )
        except Exception:
            pass
