"""
Middleware for AI4ICore Observability Plugin

Handles request tracking, service detection, and metrics collection.
"""
import time
import jwt
import json
import base64
import io
import wave
import logging
from urllib.parse import quote
from collections import OrderedDict
from typing import Optional, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from ai4icore_env import app_env

from .config import PluginConfig
from .metrics import MetricsCollector
import httpx

logger = logging.getLogger(__name__)

_CACHE_MISS = object()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking requests and collecting metrics."""
    
    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None, 
                 config: Optional[PluginConfig] = None):
        """Initialize middleware."""
        super().__init__(app)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.config = config or PluginConfig()

        # In-memory caches (best-effort) to keep tenant/org resolution out of the hot path.
        # IMPORTANT: caches are bounded (LRU) to avoid unbounded growth.
        self._tenant_org_cache: "OrderedDict[str, tuple[Optional[str], float]]" = OrderedDict()
        self._user_tenant_cache: "OrderedDict[int, tuple[Optional[Dict[str, Optional[str]]], float]]" = OrderedDict()
        self._tenant_cache_ttl_seconds: int = int(getattr(self.config, "tenant_cache_ttl_seconds", 300) or 300)
        self._tenant_org_cache_maxsize: int = int(getattr(self.config, "tenant_org_cache_maxsize", 5000) or 5000)
        self._user_tenant_cache_maxsize: int = int(getattr(self.config, "user_tenant_cache_maxsize", 10000) or 10000)

        # Shared http client for connection pooling / reuse.
        self._resolve_timeout_seconds: float = float(getattr(self.config, "multi_tenant_resolve_timeout_seconds", 2.0) or 2.0)
        self._http: Optional[httpx.AsyncClient] = None
        self._app = app
        if hasattr(app, "add_event_handler"):
            try:
                app.add_event_handler("shutdown", self._close_http_client)  # type: ignore[attr-defined]
            except Exception:
                # Best effort only: app may not be a FastAPI instance in some deployments.
                pass

    async def _close_http_client(self) -> None:
        if self._http is not None:
            try:
                await self._http.aclose()
            finally:
                self._http = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            # Use a single client so connection pools are reused between requests.
            self._http = httpx.AsyncClient(timeout=self._resolve_timeout_seconds)
        return self._http

    @staticmethod
    def _cache_get(cache: "OrderedDict[Any, tuple[Any, float]]", key: Any, now: float):
        """LRU + TTL cache get.

        Returns cached value (including None) if present and not expired,
        otherwise returns the _CACHE_MISS sentinel.
        """
        entry = cache.get(key)
        if entry is None:
            return _CACHE_MISS
        value, expires_at = entry
        if expires_at <= now:
            cache.pop(key, None)
            return _CACHE_MISS
        cache.move_to_end(key)
        return value

    @staticmethod
    def _cache_set(
        cache: "OrderedDict[Any, tuple[Any, float]]",
        key: Any,
        value: Any,
        expires_at: float,
        maxsize: int,
    ) -> None:
        """LRU + TTL cache set with max-size eviction."""
        cache[key] = (value, expires_at)
        cache.move_to_end(key)
        while maxsize > 0 and len(cache) > maxsize:
            cache.popitem(last=False)
    
    async def dispatch(self, request: Request, call_next):
        """Process request through middleware."""
        if not self.config.enabled:
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract metadata from request
        path = request.url.path
        method = request.method
        headers = request.headers
        
        # --- Priority 1 & 2: org from X-Customer-ID header or JWT 'name' claim ---
        organization, app = self._extract_customer_app(request)

        # --- Resolve tenant_id AND organization_name from the multi-tenant service ---
        tenant_id, tenant_org_name = await self._extract_tenant_info(request)

        # --- Priority 3: if org still unknown, use the tenant's organization name ---
        # For users that don't belong to any tenant, organization stays None.
        if organization is None:
            organization = tenant_org_name  # None when user is a non-tenant individual

        # Normalize for Prometheus label: None/empty → "unknown" (backward compatible with existing dashboards)
        organization_label = organization if organization else "unknown"

        # Normalize tenant label (backward compatible with existing dashboards)
        tenant = str(tenant_id) if tenant_id else "unknown"

        # Store resolved values in request.state for downstream middlewares / handlers
        # IMPORTANT: Set this BEFORE await call_next() so it's available to inner middlewares
        request.state.organization = organization_label
        request.state.tenant_id = tenant_id

        # Ensure trace spans always contain organization / tenant_id attributes.
        # Some server spans may start before contextvars are set, so we set attributes
        # directly on the current span as well.
        try:
            from opentelemetry import trace

            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("organization", organization_label)
                current_span.set_attribute("tenant_id", tenant)
        except Exception:
            # Best-effort only; tracing may not be configured in all deployments
            pass
        
        # Set organization in logging context for log formatter
        try:
            from ai4icore_logging.context import set_organization, set_tenant_id, get_tenant_id
            set_organization(organization_label)
            set_tenant_id(tenant_id)
            # Verify it was set correctly
            actual_tenant_id = get_tenant_id()
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] Set tenant_id in logging context: {tenant_id}, verified: {actual_tenant_id}")
                logger.debug(f"Set organization in logging context: {organization_label}, tenant_id: {tenant_id}")
        except Exception as e:
            # Log error for debugging
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] ❌ Failed to set tenant_id in context: {e}", exc_info=True)
            if self.config.debug:
                logger.debug(f"Failed to set organization/tenant_id in context: {e}", exc_info=True)
            pass
        
        # Initialize body_bytes variable for potential reuse
        body_bytes = None
        body_already_read = False
                
                
        if method == "POST" and (path.endswith("/pipeline") or path == "/services/inference/pipeline") and "/pipeline/" not in path:
            # Read body to detect task type
            body_bytes = await request.body()  # FastAPI caches this automatically
            # Read body to detect task type
            body_bytes = await request.body()  # FastAPI caches this automatically
            body_already_read = True
            
            # NO MORE request._receive = receive HERE!
            
            
            # NO MORE request._receive = receive HERE!
            
            try:
                request_data = json.loads(body_bytes.decode('utf-8'))
                # Check if this is a txt-lang-detection request
                if 'pipelineTasks' in request_data and len(request_data.get('pipelineTasks', [])) > 0:
                    task_type = request_data['pipelineTasks'][0].get('taskType', '')
                    if task_type == 'txt-lang-detection':
                        path = path + '/txt-lang-detection'
                        if self.config.debug:
                            logger.debug(f"Detected txt-lang-detection in generic pipeline endpoint, updating path to: {path}")
            except Exception as e:
                if self.config.debug:
                    logger.debug(f"Failed to parse request body for pipeline detection: {e}", exc_info=True)
        
        # Detect service type
        service_type = self._detect_service_type(path)
        
        # Extract metrics from body
        # Extract metrics from body
        tts_characters = 0
        translation_characters = 0
        asr_audio_length = 0
        ocr_characters = 0
        ocr_image_size_kb = 0.0
        transliteration_characters = 0
        language_detection_characters = 0
        audio_lang_detection_length = 0
        ner_tokens = 0
        speaker_verification_length = 0
        speaker_diarization_length = 0
        language_diarization_length = 0
        
        if method == "POST" and service_type in ["tts", "translation", "asr", "ocr", "transliteration", "language_detection", "audio_lang_detection", "speaker_verification", "speaker_diarization", "language_diarization", "ner"]:
            # Read body if not already read
            if not body_already_read:
                body_bytes = await request.body()  # FastAPI caches this automatically
                
                # NO MORE request._receive = receive HERE!
            else:
                # Body already read - use cached body, DO NOT overwrite receive callable
                body_bytes = request._body if hasattr(request, '_body') else body_bytes
            
            if self.config.debug:
                logger.debug(f"The service type: {service_type}")

            # Extract metrics from the body
            if service_type == "tts":
                tts_characters = self._extract_tts_characters_from_body(body_bytes)
            elif service_type == "translation":
                translation_characters = self._extract_translation_characters_from_body(body_bytes)
            elif service_type == "asr":
                asr_audio_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "ocr":
                ocr_characters = self._extract_ocr_characters_from_body(body_bytes)
                ocr_image_size_kb = self._extract_ocr_image_size_kb_from_body(body_bytes)
            elif service_type == "transliteration":
                transliteration_characters = self._extract_transliteration_characters_from_body(body_bytes)
            elif service_type == "language_detection":
                language_detection_characters = self._extract_language_detection_characters_from_body(body_bytes)
            elif service_type == "audio_lang_detection":
                audio_lang_detection_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "speaker_verification":
                speaker_verification_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "speaker_diarization":
                speaker_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "language_diarization":
                language_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
            elif service_type == "ner":
                ner_tokens = self._extract_ner_tokens_from_body(body_bytes)

            if language_detection_characters > 0 and self.config.debug:
                logger.debug(f"LANG_DET_CHARS_EXTRACTED={language_detection_characters}")
        
        # Debug logging
        if self.config.debug:
            logger.debug(f"Request: {method} {path} -> Service: {service_type}, Organization: {organization_label}, App: {app}")
        
        # Process request
        response = await call_next(request)

        # Extract service_id resolved by model-management middleware (set in request.state)
        service_id = getattr(request.state, "service_id", "") or ""

        # Calculate duration and track metrics
        duration = time.time() - start_time
        # Calculate duration and track metrics
        duration = time.time() - start_time
        # Track request
        try:
            # Debug: Log the full path being used for metrics
            if self.config.debug:
                logger.debug(f"Tracking metrics for endpoint: {path}, service_type: {service_type}")

            self.metrics_collector.track_request(
                organization=organization_label,
                app=app,
                method=method,
                endpoint=path,
                status_code=response.status_code,
                duration=duration,
                service_type=service_type,
                tenant=tenant,
                service_id=service_id,
            )

            # Track additional metrics based on service type
            self._track_additional_metrics(organization_label, app, tenant, service_type, path, duration, tts_characters, translation_characters, asr_audio_length, ocr_characters, ocr_image_size_kb, transliteration_characters, language_detection_characters, audio_lang_detection_length, ner_tokens, speaker_verification_length, speaker_diarization_length, language_diarization_length, service_id=service_id)
            
        except Exception as e:
            # Don't let metrics collection break the request
            if self.config.debug:
                logger.debug(f"Metrics collection failed: {e}", exc_info=True)

        return response
    
    def _decode_jwt_token(self, authorization_header: str) -> Optional[Dict[str, Any]]:
        """Decode JWT token from authorization header."""
        try:
            # Extract token from "Bearer <token>" format
            if not authorization_header.startswith("Bearer "):
                return None
            
            token = authorization_header[7:]  # Remove "Bearer " prefix
            
            # Decode without verification to get claims (for customer name extraction)
            # In production, you might want to verify the token with proper secret
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            
            return decoded_token
        except Exception as e:
            # Always log JWT decoding failures with ERROR level for debugging
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] ❌ JWT decoding failed: {type(e).__name__}: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _extract_organization_name(payload: Dict[str, Any]) -> Optional[str]:
        """Extract organization name from a tenant payload using a single, shared rule.

        The canonical field should be defined by the multi-tenant service API contract.
        We keep a small set of fallbacks for backward compatibility.
        """
        value = (
            payload.get("organization_name")
            or payload.get("organization")
            or payload.get("org_name")
            or payload.get("tenant_name")
            or payload.get("name")
        )
        return str(value) if value else None

    def _get_multi_tenant_service_url(self) -> Optional[str]:
        """Resolve multi-tenant service base URL from config/env with a single shared rule."""
        multi_tenant_service_url = getattr(self.config, "multi_tenant_service_url", None)
        if not multi_tenant_service_url:
            multi_tenant_service_url = app_env.multi_tenant_service_url

        if not multi_tenant_service_url:
            # Fall back to service discovery defaults when env vars are unset.
            service_name = (app_env.multi_tenant_service_name or "").strip() or "multi-tenant-service"
            service_port = (app_env.multi_tenant_service_port or "").strip() or "8001"
            service_scheme = (app_env.multi_tenant_service_scheme or "").strip() or "http"
            multi_tenant_service_url = f"{service_scheme}://{service_name}:{service_port}"
        return multi_tenant_service_url or None
    
    def _extract_customer_from_token(self, request: Request) -> Optional[str]:
        """Extract customer/organization name from JWT token in authorization header.

        Only uses the 'name' field (explicit organization identifier).
        Numeric 'sub' fields (user IDs) are intentionally ignored — organization is
        resolved dynamically from tenant data instead of a static list.
        """
        auth_header = request.headers.get("authorization", "")

        if auth_header:
            decoded_token = self._decode_jwt_token(auth_header)
            if decoded_token:
                # Use 'name' field only — must be a non-empty, non-numeric string
                customer_name = decoded_token.get("name")
                if customer_name and not str(customer_name).isdigit():
                    if self.config.debug:
                        logger.debug(f"Extracted customer from JWT 'name': {customer_name}")
                    return str(customer_name)

        return None
    
    async def _extract_tenant_info(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """
        Extract tenant_id and organization_name for the requesting user.

        Resolution order:
        1. ``tenant_id`` claim in the JWT  →  organization looked up via API (or from JWT).
        2. ``sub`` (numeric user ID) in JWT  →  both resolved via multi-tenant service API.
        3. No JWT / no tenant  →  (None, None) — the user is a non-tenant (individual) user.

        Returns:
            (tenant_id, organization_name)
            Both are ``None`` when the user does not belong to any tenant.
        """
        if self.config.debug:
            logger.debug(f"[TENANT_DEBUG] _extract_tenant_info called for path: {request.url.path}")

        auth_header = request.headers.get("authorization", "")
        if self.config.debug:
            logger.debug(f"[TENANT_DEBUG] Auth header present: {bool(auth_header)}, length: {len(auth_header) if auth_header else 0}")

        if auth_header:
            decoded_token = self._decode_jwt_token(auth_header)
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] JWT decoded: success={bool(decoded_token)}")

            if decoded_token:
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] JWT payload keys: {list(decoded_token.keys())}")

                # --- Priority 1: tenant_id is directly present in the JWT ---
                tenant_id = decoded_token.get("tenant_id")
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] Extracted tenant_id from JWT: {tenant_id} (type: {type(tenant_id)})")

                if tenant_id is not None and tenant_id != "":
                    # Org name may also be carried in the JWT itself
                    organization_name = self._extract_organization_name(decoded_token)
                    if self.config.debug:
                        logger.debug(
                            f"[TENANT_DEBUG] ✅ tenant_id from JWT: {tenant_id}, "
                            f"organization_name from JWT: {organization_name}"
                        )
                    # If org name was not in the JWT, resolve from the multi-tenant service
                    if not organization_name:
                        organization_name = await self._resolve_organization_from_tenant_id(str(tenant_id), request)
                    return str(tenant_id), organization_name

                # --- Priority 2: resolve from numeric user_id ('sub') ---
                user_id = decoded_token.get("sub")
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] JWT has no tenant_id. Checking 'sub' field: {user_id} (type: {type(user_id)})")

                if user_id:
                    try:
                        if isinstance(user_id, str):
                            user_id_int = int(user_id) if user_id.isdigit() else None
                            if user_id_int is None and self.config.debug:
                                logger.debug(f"[TENANT_DEBUG] user_id '{user_id}' is not numeric, cannot resolve tenant")
                        else:
                            user_id_int = int(user_id)

                        if user_id_int:
                            if self.config.debug:
                                logger.debug(f"[TENANT_DEBUG] Resolving tenant info for user_id={user_id_int} via API")
                            tenant_info = await self._resolve_tenant_from_user_id(user_id_int, request)
                            if tenant_info:
                                resolved_tid = tenant_info.get("tenant_id")
                                resolved_org = tenant_info.get("organization_name")
                                if not resolved_org and resolved_tid:
                                    resolved_org = await self._resolve_organization_from_tenant_id(str(resolved_tid), request)
                                if self.config.debug:
                                    logger.debug(
                                        f"[TENANT_DEBUG] ✅ Resolved tenant_id={resolved_tid}, "
                                        f"organization_name={resolved_org} for user_id={user_id_int}"
                                    )
                                return resolved_tid, resolved_org
                            else:
                                if self.config.debug:
                                    logger.debug(f"[TENANT_DEBUG] No tenant found for user_id={user_id_int} (non-tenant user)")
                        else:
                            if self.config.debug:
                                logger.debug("[TENANT_DEBUG] user_id_int is None, cannot resolve tenant")
                    except (ValueError, TypeError) as e:
                        if self.config.debug:
                            logger.debug(f"[TENANT_DEBUG] Exception converting user_id to int: {user_id}, error: {e}", exc_info=True)
                else:
                    if self.config.debug:
                        logger.debug("[TENANT_DEBUG] JWT has no 'sub' field, cannot resolve tenant from user_id")

        # Non-tenant user (individual user with no tenant association)
        if self.config.debug:
            logger.debug("[TENANT_DEBUG] No tenant_id resolved — treating as non-tenant user (org=None)")
        return None, None
    
    async def _resolve_tenant_from_user_id(self, user_id: int, request: Request) -> Optional[Dict[str, Optional[str]]]:
        """
        Resolve tenant information from user_id by calling the multi-tenant service API.

        Args:
            user_id: The user ID from JWT token
            request: The request object to forward auth headers

        Returns:
            A dict with keys ``tenant_id`` and ``organization_name`` when the user
            belongs to a tenant, or ``None`` when no tenant is found or the call fails.
            Example: {"tenant_id": "42", "organization_name": "acme-corp"}
        """
        try:
            now = time.time()
            cached = self._cache_get(self._user_tenant_cache, user_id, now)
            if cached is not _CACHE_MISS:
                return cached

            # Resolve multi-tenant service URL from config or environment / service discovery
            multi_tenant_service_url = self._get_multi_tenant_service_url()

            if not multi_tenant_service_url:
                logger.error("Cannot determine multi-tenant service URL. Set MULTI_TENANT_SERVICE_URL or MULTI_TENANT_SERVICE_NAME environment variable.")
                return None

            resolve_url = f"{multi_tenant_service_url}/resolve/tenant/from/user?user_id={user_id}"

            if self.config.debug:
                logger.debug(f"Resolving tenant info for user_id {user_id} via {resolve_url}")

            # Forward auth headers from original request
            headers: Dict[str, str] = {}
            auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
            if auth_header:
                headers["Authorization"] = auth_header
            api_key = request.headers.get("X-API-Key")
            if api_key:
                headers["X-API-Key"] = api_key

            client = self._get_http_client()
            response = await client.get(resolve_url, headers=headers)

            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] API Response status: {response.status_code}")

            if response.status_code == 200:
                tenant_data = response.json()
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] API Response data: {tenant_data}")

                tenant_id = tenant_data.get("tenant_id")
                if not tenant_id:
                    if self.config.debug:
                        logger.debug(f"[TENANT_DEBUG] ❌ Tenant data returned but no tenant_id field for user_id {user_id}: {tenant_data}")
                    # Do NOT cache transient schema issues; just degrade gracefully.
                    return None

                # Extract organization name — try several common field names that the
                # multi-tenant service may return.
                organization_name = self._extract_organization_name(tenant_data)

                if self.config.debug:
                    logger.debug(
                        f"[TENANT_DEBUG] ✅ Resolved tenant_id={tenant_id}, "
                        f"organization_name={organization_name} for user_id={user_id}"
                    )
                tenant_info = {"tenant_id": str(tenant_id), "organization_name": organization_name}
                self._cache_set(
                    self._user_tenant_cache,
                    user_id,
                    tenant_info,
                    now + self._tenant_cache_ttl_seconds,
                    self._user_tenant_cache_maxsize,
                )
                return tenant_info

            if response.status_code == 404:
                # True negative: user has no tenant — safe to cache.
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] User user_id={user_id} has no tenant (404)")
                self._cache_set(
                    self._user_tenant_cache,
                    user_id,
                    None,
                    now + self._tenant_cache_ttl_seconds,
                    self._user_tenant_cache_maxsize,
                )
                return None

            # Transient failure (5xx/401/403/etc) — do NOT cache None.
            error_detail = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
            if self.config.debug:
                logger.debug(
                    f"[TENANT_DEBUG] ❌ Failed to resolve tenant for user_id {user_id}: "
                    f"HTTP {response.status_code} - {error_detail}"
                )
            return None

        except httpx.TimeoutException as e:
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] ❌ Timeout resolving tenant for user_id {user_id} (exceeded 5s): {e}")
            return None
        except httpx.ConnectError as e:
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] ❌ Connection error resolving tenant for user_id {user_id}: {e}")
            return None
        except httpx.RequestError as e:
            if self.config.debug:
                logger.debug(
                    f"[TENANT_DEBUG] ❌ Request error resolving tenant for user_id {user_id}: {type(e).__name__}: {e}"
                )
            return None
        except Exception as e:
            if self.config.debug:
                logger.debug(
                    f"[TENANT_DEBUG] ❌ Unexpected error resolving tenant from user_id {user_id}: {type(e).__name__}: {e}",
                    exc_info=True,
                )
            return None

    async def _resolve_organization_from_tenant_id(self, tenant_id: str, request: Request) -> Optional[str]:
        """
        Resolve organization name by tenant_id.

        The multi-tenant "resolve tenant from user" endpoint returns tenant_id and
        schema/subscriptions, but does not include organization_name. This method
        calls a tenant details endpoint to fetch organization_name so metrics/logs
        can be labeled dynamically.
        """
        try:
            tenant_id_str = str(tenant_id)
            now = time.time()
            cached = self._cache_get(self._tenant_org_cache, tenant_id_str, now)
            if cached is not _CACHE_MISS:
                return cached

            multi_tenant_service_url = self._get_multi_tenant_service_url()

            if not multi_tenant_service_url:
                logger.error(
                    "Cannot determine multi-tenant service URL. Set MULTI_TENANT_SERVICE_URL or MULTI_TENANT_SERVICE_NAME environment variable."
                )
                return None

            encoded_tenant_id = quote(str(tenant_id), safe="")

            headers: Dict[str, str] = {}
            auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
            if auth_header:
                headers["Authorization"] = auth_header
            api_key = request.headers.get("X-API-Key")
            if api_key:
                headers["X-API-Key"] = api_key

            # Candidate endpoints should be configurable to avoid unbounded retries in production.
            configured_candidates = getattr(self.config, "multi_tenant_tenant_details_candidates", None)
            if isinstance(configured_candidates, (list, tuple)) and configured_candidates:
                candidates = [str(c).format(base=multi_tenant_service_url, tenant_id=encoded_tenant_id) for c in configured_candidates]
            else:
                # Default candidates (kept for backward compatibility).
                candidates = [
                    f"{multi_tenant_service_url}/internal/view/tenant?tenant_id={encoded_tenant_id}",
                    f"{multi_tenant_service_url}/admin/view/tenant?tenant_id={encoded_tenant_id}",
                ]

            client = self._get_http_client()
            for resolve_url in candidates:
                if self.config.debug:
                    logger.debug(f"[TENANT_DEBUG] Resolving organization for tenant_id={tenant_id} via {resolve_url}")

                response = await client.get(resolve_url, headers=headers)
                if response.status_code == 200:
                    tenant_data = response.json()
                    organization_name = self._extract_organization_name(tenant_data)
                    if organization_name:
                        org_str = str(organization_name)
                        self._cache_set(
                            self._tenant_org_cache,
                            tenant_id_str,
                            org_str,
                            now + self._tenant_cache_ttl_seconds,
                            self._tenant_org_cache_maxsize,
                        )
                        return org_str
                    # Avoid caching None for long on ambiguous responses.
                    return None
                if response.status_code in (401, 403, 404):
                    continue

            # If we got 404 across all candidates, treat as true negative and cache None.
            self._cache_set(
                self._tenant_org_cache,
                tenant_id_str,
                None,
                now + self._tenant_cache_ttl_seconds,
                self._tenant_org_cache_maxsize,
            )
            return None
        except httpx.TimeoutException as e:
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] Timeout resolving organization for tenant_id={tenant_id}: {e}")
            return None
        except httpx.RequestError as e:
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] Request error resolving organization for tenant_id={tenant_id}: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            if self.config.debug:
                logger.debug(
                    f"[TENANT_DEBUG] Unexpected error resolving organization for tenant_id={tenant_id}: {type(e).__name__}: {e}",
                    exc_info=True,
                )
            return None
    
    def _extract_customer_app(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """Extract organization and app from request headers and JWT token.

        Priority order:
        1. X-Customer-ID header (explicit organization identifier - highest priority)
        2. JWT token claims (non-numeric 'name' field)
        3. Returns None — organization will be resolved dynamically from tenant data in dispatch()
        """
        organization: Optional[str] = None

        # PRIORITY 1: Check X-Customer-ID first (explicit organization identifier)
        customer_id_header = request.headers.get("X-Customer-ID")
        if customer_id_header:
            organization = customer_id_header
            if self.config.debug:
                logger.debug(f"Found organization from X-Customer-ID header: {organization}")
        else:
            # PRIORITY 2: Try JWT token extraction
            if self.config.debug:
                logger.debug("No X-Customer-ID found, trying JWT token extraction...")
            organization = self._extract_customer_from_token(request)

        # NOTE: No random fallback — if organization is still None, it will be populated
        # in dispatch() from the resolved tenant name. Non-tenant users will have org=None.
        if organization is None and self.config.debug:
            logger.debug("No organization determined from header/JWT; will resolve from tenant data.")

        # Get app from header or use "unknown"
        app = request.headers.get("X-App-ID")
        if app is None:
            app = "unknown"

        return organization, app
    
    def _detect_service_type(self, path: str) -> str:
        """Detect service type from URL path."""
        path_lower = path.lower()
        
        # IMPORTANT: Check specific endpoints FIRST before generic patterns
        # This ensures specific endpoints are matched correctly and the full path is preserved in metrics
        
        # Dedicated text language detection endpoint (txt-lang-detection) - check FIRST
        if any(pattern in path_lower for pattern in ["/services/inference/txt-lang-detection", "/inference/txt-lang-detection", "/txt-lang-detection"]):
            return "language_detection"
        # Pipeline text language detection endpoint (txt-lang-detection) - check SECOND
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/txt-lang-detection", "/services/inference/pipeline/txt-language-detection", "/pipeline/txt-lang-detection"]):
            return "language_detection"
        # Pipeline OCR endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/ocr", "/pipeline/ocr"]):
            return "ocr"
        # Pipeline Transliteration endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/transliteration", "/services/inference/pipeline/translation/transliteration", "/pipeline/transliteration", "/pipeline/translation/transliteration"]):
            return "transliteration"
        # Pipeline audio language detection endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/audio-lang-detection", "/services/inference/pipeline/audio-language-detection", "/pipeline/audio-lang-detection"]):
            return "audio_lang_detection"
        # Pipeline speaker verification endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-verification", "/pipeline/speaker-verification"]):
            return "speaker_verification"
        # Pipeline speaker diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-diarization", "/pipeline/speaker-diarization"]):
            return "speaker_diarization"
        # Pipeline language diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/language-diarization", "/pipeline/language-diarization"]):
            return "language_diarization"
        
        # Then check for generic service patterns (non-pipeline endpoints)
        elif any(pattern in path_lower for pattern in ["/translation", "/nmt", "/translate"]):
            return "translation"
        elif any(pattern in path_lower for pattern in ["/asr", "/transcribe", "/speech"]):
            return "asr"
        elif any(pattern in path_lower for pattern in ["/tts", "/synthesize"]):
            return "tts"
        elif any(pattern in path_lower for pattern in ["/ocr", "/text-recognition"]):
            return "ocr"
        elif any(pattern in path_lower for pattern in ["/transliteration", "/xlit", "/transliterate"]):
            return "transliteration"
        elif any(pattern in path_lower for pattern in ["/audio-lang-detection", "/audio-language-detection", "/audio-detect"]):
            return "audio_lang_detection"
        elif any(pattern in path_lower for pattern in ["/language-detection", "/lang-detect", "/detect-language"]):
            return "language_detection"
        elif any(pattern in path_lower for pattern in ["/language-diarization", "/language-diarization-compute-call"]):
            return "language_diarization"
        elif any(pattern in path_lower for pattern in ["/speaker-diarization", "/speaker-diarization-compute-call"]):
            return "speaker_diarization"
        elif any(pattern in path_lower for pattern in ["/ner", "/entity", "/entities"]):
            return "ner"
        elif any(pattern in path_lower for pattern in ["/speaker", "/speaker-enrollment", "/speaker-verification", "/speak"]):
            return "speaker_verification"
        elif any(pattern in path_lower for pattern in ["/llm", "/generate", "/chat", "/completion"]):
            return "llm"
        elif any(pattern in path_lower for pattern in ["/enterprise", "/health", "/metrics", "/config"]):
            return "enterprise"
        elif any(pattern in path_lower for pattern in ["/docs", "/openapi", "/redoc"]):
            return "documentation"
        else:
            return "unknown"
    
    def _track_additional_metrics(self, organization: str, app: str, tenant: str, service_type: str, path: str, duration: float, tts_characters: int = 0, translation_characters: int = 0, asr_audio_length: float = 0, ocr_characters: int = 0, ocr_image_size_kb: float = 0.0, transliteration_characters: int = 0, language_detection_characters: int = 0, audio_lang_detection_length: float = 0, ner_tokens: int = 0, speaker_verification_length: float = 0, speaker_diarization_length: float = 0, language_diarization_length: float = 0, service_id: str = ""):
        """Track additional metrics based on service type."""
        try:
            # Track component latency
            self.metrics_collector.track_component_latency(
                organization=organization,
                app=app,
                component=service_type,
                duration=duration,
                tenant=tenant,
            )
            
            # Track data processing based on service type
            if service_type == "llm":
                # Mock LLM token processing
                tokens = self._estimate_llm_tokens(path)
                self.metrics_collector.track_llm_tokens(
                    organization=organization,
                    app=app,
                    model="gpt-3.5-turbo",  # Mock model
                    tokens=tokens,
                    tenant=tenant,
                )
            elif service_type == "tts":
                # Track real TTS character count
                if tts_characters > 0:
                    self.metrics_collector.track_tts_characters(
                        organization=organization,
                        app=app,
                        language="en",  # Default language
                        characters=tts_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real TTS characters: {tts_characters}")
            elif service_type == "translation":
                # Track real translation character count
                if translation_characters > 0:
                    self.metrics_collector.track_nmt_characters(
                        organization=organization,
                        app=app,
                        source_lang="en",  # Default source language
                        target_lang="hi",  # Default target language
                        characters=translation_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real translation characters: {translation_characters}")
            elif service_type == "asr":
                # Track real ASR audio length
                if asr_audio_length > 0:
                    self.metrics_collector.track_asr_audio_length(
                        organization=organization,
                        app=app,
                        language="en",  # Default language
                        audio_seconds=asr_audio_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real ASR audio length: {asr_audio_length:.2f} seconds")
            elif service_type == "ocr":
                # Track real OCR character count
                if ocr_characters > 0:
                    self.metrics_collector.track_ocr_characters(
                        organization=organization,
                        app=app,
                        characters=ocr_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real OCR characters: {ocr_characters}")
                # Track OCR image payload size in KB
                if ocr_image_size_kb > 0:
                    self.metrics_collector.track_ocr_image_size(
                        organization=organization,
                        app=app,
                        image_size_kb=ocr_image_size_kb,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked OCR image size: {ocr_image_size_kb:.2f} KB")
            elif service_type == "transliteration":
                # Track real transliteration character count
                if transliteration_characters > 0:
                    self.metrics_collector.track_transliteration_characters(
                        organization=organization,
                        app=app,
                        source_lang="en",  # Default source language
                        target_lang="hi",  # Default target language
                        characters=transliteration_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real transliteration characters: {transliteration_characters}")
            elif service_type == "language_detection":
                # Track real language detection character count
                if language_detection_characters > 0:
                    self.metrics_collector.track_language_detection_characters(
                        organization=organization,
                        app=app,
                        characters=language_detection_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real language detection characters: {language_detection_characters}")
            elif service_type == "audio_lang_detection":
                # Track real audio language detection audio length
                if audio_lang_detection_length > 0:
                    self.metrics_collector.track_audio_lang_detection_length(
                        organization=organization,
                        app=app,
                        audio_seconds=audio_lang_detection_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real audio language detection audio length: {audio_lang_detection_length:.2f} seconds")
            elif service_type == "ner":
                # Track real NER token (word) count
                if ner_tokens > 0:
                    self.metrics_collector.track_ner_tokens(
                        organization=organization,
                        app=app,
                        tokens=ner_tokens,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real NER tokens (words): {ner_tokens}")
            elif service_type == "speaker_verification":
                # Track real speaker verification audio length
                if speaker_verification_length > 0:
                    self.metrics_collector.track_speaker_verification_length(
                        organization=organization,
                        app=app,
                        audio_seconds=speaker_verification_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real speaker verification audio length: {speaker_verification_length:.2f} seconds")
            elif service_type == "speaker_diarization":
                # Track real speaker diarization audio length
                if speaker_diarization_length > 0:
                    self.metrics_collector.track_speaker_diarization_length(
                        organization=organization,
                        app=app,
                        audio_seconds=speaker_diarization_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real speaker diarization audio length: {speaker_diarization_length:.2f} seconds")
            elif service_type == "language_diarization":
                # Track real language diarization audio length
                if language_diarization_length > 0:
                    self.metrics_collector.track_language_diarization_length(
                        organization=organization,
                        app=app,
                        audio_seconds=language_diarization_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
                    if self.config.debug:
                        print(f"📊 Tracked real language diarization audio length: {language_diarization_length:.2f} seconds")
            
            # Update SLA compliance (mock calculation)
            compliance = self._calculate_sla_compliance(service_type, duration)
            self.metrics_collector.update_sla_compliance(
                organization=organization,
                app=app,
                sla_type=f"{service_type}_availability",
                compliance_percent=compliance,
                tenant=tenant,
            )
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Additional metrics tracking failed: {e}")
    
    def _estimate_llm_tokens(self, path: str) -> int:
        """Estimate LLM tokens based on path."""
        # Mock estimation - in real implementation, this would analyze request content
        return 100  # Mock value
    
    def _extract_tts_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from TTS request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from TTS input
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract TTS characters: {e}")
            return 0
    
    def _extract_translation_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from translation request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from translation input
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract translation characters: {e}")
            return 0
    
    def _extract_ocr_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from OCR request body (from image text)."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from OCR input (assuming image base64 data)
            total_characters = 0
            
            # OCR uses pipeline format: {"inputData": {"image": [...]}, ...}
            if 'inputData' in request_data and 'image' in request_data['inputData']:
                for image_item in request_data['inputData']['image']:
                    # Handle imageContent (base64 encoded image)
                    if 'imageContent' in image_item:
                        content = image_item['imageContent']
                        # Estimate characters: each base64 char represents ~0.75 bytes of actual data
                        # OCR typically extracts 5-10% of image data as text
                        estimated_chars = len(content) // 200  # Conservative estimate
                        total_characters += estimated_chars
                        if self.config.debug:
                            print(f"🔍 OCR imageContent length: {len(content)}, estimated chars: {estimated_chars}")
                    # Handle imageUri (URL to image)
                    elif 'imageUri' in image_item:
                        image_uri = image_item['imageUri']
                        try:
                            # Download image from URL to estimate size
                            response = httpx.get(image_uri, timeout=5.0, follow_redirects=True)
                            if response.status_code == 200:
                                image_data = response.content
                                # Estimate characters based on image size
                                # Rough estimate: ~1000 bytes per character for typical images
                                estimated_chars = len(image_data) // 1000
                                total_characters += estimated_chars
                                if self.config.debug:
                                    print(f"🔍 OCR imageUri downloaded: {len(image_data)} bytes, estimated chars: {estimated_chars}")
                            else:
                                if self.config.debug:
                                    print(f"⚠️ Failed to download image from URI: {response.status_code}")
                        except Exception as e:
                            if self.config.debug:
                                print(f"⚠️ Error downloading image from URI: {e}")
                        
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract OCR characters: {e}")
            return 0
    
    def _extract_transliteration_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from transliteration request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from transliteration input
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])

            if self.config.debug and total_characters > 0:
                print(f"🔤 Transliteration characters extracted: {total_characters}")
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract transliteration characters: {e}")
            return 0
    
    def _extract_language_detection_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from language detection request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract character count from language detection input
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])

            if self.config.debug:
                print(f"🔤 Language detection characters extracted: {total_characters}")
            
            return total_characters
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract language detection characters: {e}")
            return 0
    
    def _extract_ner_tokens_from_body(self, body_bytes: bytes) -> int:
        """Extract real token (word) count from NER request body."""
        try:
            if not body_bytes:
                return 0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract token (word) count from NER input
            total_tokens = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        source_text = input_item['source']
                        # Count words by splitting on whitespace
                        # This handles multiple spaces, tabs, newlines, etc.
                        words = source_text.split()
                        total_tokens += len(words)
            
            return total_tokens
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract NER tokens: {e}")
            return 0
    
    def _extract_asr_audio_length_from_body(self, body_bytes: bytes) -> float:
        """Extract real audio length in seconds from ASR request body."""
        try:
            if not body_bytes:
                return 0.0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            # Extract audio length from ASR input
            total_audio_length = 0.0
            audio_items_found = 0
            
            # Check for standard ASR format: {"audio": [...], "config": {...}}
            if 'audio' in request_data:
                for audio_item in request_data['audio']:
                    if 'audioContent' in audio_item:
                        # Decode base64 audio and calculate length
                        audio_length = self._calculate_audio_length_from_base64(audio_item['audioContent'])
                        total_audio_length += audio_length
                        audio_items_found += 1
                        if self.config.debug:
                            print(f"🎵 ASR audio item {audio_items_found}: {audio_length:.2f} seconds")
                    elif 'audioUri' in audio_item:
                        # audioUri requires downloading the file to calculate length,
                        # which is not practical in middleware. Skip for now.
                        if self.config.debug:
                            print(f"⚠️ audioUri detected but audio length cannot be calculated from URI without downloading file")
            # Also check for pipeline format: {"inputData": {"audio": [...]}, ...}
            elif 'inputData' in request_data and 'audio' in request_data['inputData']:
                for audio_item in request_data['inputData']['audio']:
                    if 'audioContent' in audio_item:
                        # Decode base64 audio and calculate length
                        audio_length = self._calculate_audio_length_from_base64(audio_item['audioContent'])
                        total_audio_length += audio_length
                        audio_items_found += 1
                        if self.config.debug:
                            print(f"🎵 ASR audio item {audio_items_found}: {audio_length:.2f} seconds")
                    elif 'audioUri' in audio_item:
                        # audioUri requires downloading the file to calculate length,
                        # which is not practical in middleware. Skip for now.
                        if self.config.debug:
                            print(f"⚠️ audioUri detected but audio length cannot be calculated from URI without downloading file")
            else:
                if self.config.debug:
                    print(f"⚠️ ASR request structure not recognized. Keys: {list(request_data.keys())}")
            
            return total_audio_length
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract ASR audio length: {e}")
            return 0.0
    
    def _calculate_audio_length_from_base64(self, base64_audio: str) -> float:
        """Calculate audio length in seconds from base64 encoded audio."""
        try:
            # Decode base64 audio
            audio_data = base64.b64decode(base64_audio)
            
            # Create a BytesIO object to read the audio data
            audio_buffer = io.BytesIO(audio_data)
            
            # Try to read as WAV file
            with wave.open(audio_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                duration = frames / float(sample_rate)
                if self.config.debug:
                    print(f"✅ Calculated WAV audio length: {duration:.2f} seconds ({frames} frames @ {sample_rate} Hz)")
                return duration
                
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to parse as WAV file: {e}, trying fallback estimation")
            # Fallback: estimate based on data size (rough approximation)
            try:
                audio_data = base64.b64decode(base64_audio)
                # Rough estimate: 16-bit audio at 16kHz = 32KB per second
                estimated_duration = len(audio_data) / 32000
                if self.config.debug:
                    print(f"📊 Estimated audio length: {estimated_duration:.2f} seconds (based on {len(audio_data)} bytes)")
                return estimated_duration
            except Exception as fallback_error:
                if self.config.debug:
                    print(f"❌ Fallback estimation also failed: {fallback_error}")
                return 0.0
    
    def _extract_ocr_image_size_kb_from_body(self, body_bytes: bytes) -> float:
        """Extract image payload size in KB from OCR request body."""
        try:
            if not body_bytes:
                return 0.0
            
            # Parse JSON request
            request_data = json.loads(body_bytes.decode('utf-8'))
            
            total_size_kb = 0.0
            
            # Check direct OCR format: {"image": [...]}
            if 'image' in request_data:
                for image_item in request_data['image']:
                    if 'imageContent' in image_item:
                        # Calculate size from base64 string
                        total_size_kb += len(image_item['imageContent']) / 1024
            
            # Check pipeline format: {"inputData": {"image": [...]}}
            if 'inputData' in request_data and 'image' in request_data['inputData']:
                for image_item in request_data['inputData']['image']:
                    if 'imageContent' in image_item:
                        # Calculate size from base64 string
                        total_size_kb += len(image_item['imageContent']) / 1024
            
            return total_size_kb
            
        except Exception as e:
            if self.config.debug:
                print(f"⚠️ Failed to extract OCR image size: {e}")
            return 0.0

    def _calculate_sla_compliance(self, service_type: str, duration: float) -> float:
        """Calculate SLA compliance based on service type and duration."""
        # Mock SLA compliance calculation
        if service_type == "llm":
            return 99.5 if duration < 2.0 else 95.0
        elif service_type == "tts":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "translation":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "asr":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ocr":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "transliteration":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "language_detection":
            return 99.9 if duration < 0.3 else 98.5
        elif service_type == "audio_lang_detection":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ner":
            return 99.8 if duration < 0.8 else 97.5
        elif service_type == "speaker_verification":
            return 99.6 if duration < 2.0 else 95.5
        elif service_type == "speaker_diarization":
            return 99.5 if duration < 3.0 else 95.0
        elif service_type == "language_diarization":
            return 99.6 if duration < 2.5 else 95.5
        else:
            return 99.0


