"""
Standalone Smart Model Router (SMR) microservice.

This service exposes an API that:
- Accepts an inference payload (e.g. NMT request body) plus task_type
- Receives user auth token and policy headers
- Calls Policy Engine + Model Management to choose the best serviceId
- Returns the selected serviceId (and optional policy metadata)

Initial version is intentionally small and focused so it can be called
from any downstream service (e.g. nmt-service) via HTTP.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

# Import DB operations for direct database access
from db_operations import list_all_services, list_services_with_policies, get_model_details

# Import scoring/selection logic
from scoring import (
    _compute_latency_score_for_service,
    _get_cost_tier_value,
    _compute_policy_match_score_for_service,
    validate_policy_combinations,
    select_service_deterministically,
    compute_profiler_match_score,
    select_service_by_profiler,
)

try:
    from ai4icore_logging import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover - fallback logging
    import logging

    logger = logging.getLogger(__name__)


POLICY_ENGINE_URL = os.getenv("POLICY_ENGINE_URL", "http://policy-engine:8095")
MODEL_MANAGEMENT_SERVICE_URL = os.getenv(
    "MODEL_MANAGEMENT_SERVICE_URL", "http://model-management-service:8091"
)
REQUEST_PROFILER_SERVICE_URL = os.getenv(
    "REQUEST_PROFILER_SERVICE_URL", "http://request-profiler-service:8000"
)


class SMRSelectRequest(BaseModel):
    """Request schema for SMR service selection."""

    task_type: str
    # Full original inference payload from caller (e.g. NMTInferenceRequest)
    request_body: Dict[str, Any]
    # Optional context provided by caller so SMR doesn't need to decode JWT again
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    # Note: Policy values (latency_policy, cost_policy, accuracy_policy) should be passed
    # via HTTP headers (X-Latency-Policy, X-Cost-Policy, X-Accuracy-Policy) for highest priority


class SMRSelectResponse(BaseModel):
    """Response schema for SMR selection."""

    serviceId: str
    # Fallback service ID (second best service) for use when primary service fails
    fallbackServiceId: Optional[str] = None
    # Tenant ID from the request (null for free users, actual tenant_id for tenant users)
    # Note: "free-user" is used internally for Policy Engine lookup but not exposed in response
    tenant_id: Optional[str] = None
    # Whether this is a free user (no tenant_id was provided in the request)
    is_free_user: bool = False
    # Tenant policy from Policy Engine (requirements)
    tenant_policy: Optional[Dict[str, Any]] = None
    # Service policy from Model Management (selected service's characteristics)
    service_policy: Optional[Dict[str, Any]] = None
    # Scoring details (tie breaker information), null if context-aware
    scoring_details: Optional[Dict[str, Any]] = None
    # Context-aware result (only populated when context-aware is enabled for NMT)
    context_aware_result: Optional[Dict[str, Any]] = None
    # Request profiler results (only populated when X-Request-Profiler header is enabled)
    request_profiler: Optional[Dict[str, Any]] = None


app = FastAPI(
    title="Smart Model Router Service",
    version="1.0.0",
    description="Standalone SMR microservice for selecting serviceId based on policies and benchmarks.",
)


@app.get("/health")
async def health() -> Dict[str, str]:
    """Basic health endpoint for container health checks."""
    return {"status": "ok"}


async def call_policy_engine_for_smr(
    http_client: httpx.AsyncClient,
    user_id: Optional[str],
    tenant_id: Optional[str],
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str],
) -> Dict[str, Any]:
    """Call Policy Engine to evaluate latency/cost/accuracy policy for this request."""
    payload: Dict[str, Any] = {
        "user_id": user_id or "anonymous",
        "tenant_id": tenant_id,
        "latency_policy": latency_policy,
        "cost_policy": cost_policy,
        "accuracy_policy": accuracy_policy,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    logger.info(
        "SMR: Calling policy-engine for routing",
        extra={
            "context": {
                "user_id": user_id or "anonymous",
                "tenant_id": tenant_id,
                "latency_policy": latency_policy,
                "cost_policy": cost_policy,
                "accuracy_policy": accuracy_policy,
            }
        },
    )
    try:
        resp = await http_client.post(
            f"{POLICY_ENGINE_URL}/v1/policy/evaluate",
            json=payload,
            timeout=10.0,
        )
    except httpx.RequestError as e:
        logger.error(f"Policy Engine request failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "POLICY_ENGINE_UNAVAILABLE",
                "message": "Policy Engine is temporarily unavailable. Please try again.",
            },
        )

    if resp.status_code != 200:
        logger.warning(
            "Policy Engine returned non-200 status",
            extra={"status_code": resp.status_code, "body": resp.text},
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "code": "POLICY_EVALUATION_FAILED",
                "message": "Failed to evaluate routing policy.",
            },
        )

    return resp.json()


async def fetch_candidate_services_for_task(
    http_client: httpx.AsyncClient,
    task_type: str,
    headers: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch candidate services for a given task type directly from database."""
    logger.info(
        "SMR: Fetching candidate services from database",
        extra={"context": {"task_type": task_type}},
    )
    try:
        # Direct database call - no HTTP request needed
        data = await list_all_services(
            task_type=task_type,
            is_published=True,  # Only published services
            created_by=None
        )
        
        if data is None:
            logger.warning(f"No services found for task_type={task_type}")
            return []
        
        if not isinstance(data, list):
            logger.error("Unexpected response format from database (expected list)")
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "DATABASE_BAD_RESPONSE",
                    "message": "Database returned invalid response format.",
                },
            )

        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Database query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Database is temporarily unavailable. Please try again.",
            },
        )


async def fetch_policies_for_task(
    http_client: httpx.AsyncClient,
    task_type: str,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Fetch per-service policies for a given task type directly from database."""
    try:
        # Direct database call - no HTTP request needed
        services_list = await list_services_with_policies(task_type=task_type)
        
        if not isinstance(services_list, list):
            logger.warning("Unexpected policy response format from database")
            return {}

        policies_map: Dict[str, Dict[str, Any]] = {}
        for entry in services_list:
            try:
                sid = entry.get("serviceId")
                pol = entry.get("policy")
                if sid and isinstance(pol, dict):
                    policies_map[str(sid)] = pol
            except AttributeError:
                continue

        logger.info(
            "SMR: Loaded service policies from database",
            extra={
                "context": {
                    "task_type": task_type,
                    "policy_count": len(policies_map),
                }
            },
        )
        return policies_map
    except Exception as e:
        logger.warning(f"Database policy query failed: {e}", exc_info=True)
        return {}


async def call_request_profiler(
    http_client: httpx.AsyncClient,
    text: str,
) -> Dict[str, Any]:
    """
    Call request profiler service to get domain and complexity information.
    
    Args:
        http_client: HTTP client for making requests
        text: Input text to profile
        
    Returns:
        Dictionary containing domain and complexity information
    """
    try:
        profiler_payload = {"text": text}
        
        logger.info(
            "SMR: Calling request profiler service",
            extra={
                "context": {
                    "text_length": len(text),
                    "profiler_url": f"{REQUEST_PROFILER_SERVICE_URL}/api/v1/profile",
                }
            }
        )
        
        response = await http_client.post(
            f"{REQUEST_PROFILER_SERVICE_URL}/api/v1/profile",
            json=profiler_payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        response.raise_for_status()
        profiler_result = response.json()
        
        # Extract domain and complexity from profiler response
        profile = profiler_result.get("profile", {})
        domain_label = profile.get("domain", {}).get("label")
        complexity_level = profile.get("scores", {}).get("complexity_level")
        
        logger.info(
            "SMR: Request profiler returned results",
            extra={
                "context": {
                    "domain": domain_label,
                    "complexity_level": complexity_level,
                }
            }
        )
        
        return {
            "domain": domain_label,
            "complexity_level": complexity_level,
            "full_profile": profiler_result,
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "SMR: Request profiler returned error",
            extra={
                "context": {
                    "status_code": e.response.status_code,
                    "response_text": e.response.text[:500] if e.response else None,
                }
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail={
                "code": "PROFILER_SERVICE_ERROR",
                "message": f"Request profiler service error: {e.response.text[:200] if e.response else str(e)}",
            },
        )
    except httpx.RequestError as e:
        logger.error(
            "SMR: Request profiler connection error",
            extra={"context": {"error": str(e)}},
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PROFILER_SERVICE_UNAVAILABLE",
                "message": "Request profiler service is temporarily unavailable. Please try again later.",
            },
        )


async def fetch_model_domain(
    http_client: httpx.AsyncClient,
    model_id: str,
) -> Optional[List[str]]:
    """
    Fetch model domain information directly from database.
    
    Args:
        http_client: HTTP client (kept for compatibility, not used)
        model_id: Model ID to fetch domain for
        
    Returns:
        List of domain strings, or None if not found
    """
    try:
        # Direct database call - no HTTP request needed
        model_data = await get_model_details(model_id, version=None)
        
        if not model_data:
            return None
        
        domain = model_data.get("domain")
        if isinstance(domain, list):
            return domain
        elif isinstance(domain, str):
            # Handle comma-separated string format
            return [d.strip() for d in domain.split(",") if d.strip()]
        return None
        
    except Exception as e:
        logger.warning(
            f"SMR: Failed to fetch model domain for {model_id}: {e}",
            exc_info=True,
        )
        return None


async def handle_context_aware_nmt(
    http_client: httpx.AsyncClient,
    body_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle context-aware NMT by calling LLM translate API directly.
    
    Returns the translation result in NMT format.
    """
    # Language code to full name mapping
    LANGUAGE_CODE_TO_NAME = {
        "en": "English", "hi": "Hindi", "ta": "Tamil", "te": "Telugu",
        "kn": "Kannada", "ml": "Malayalam", "bn": "Bengali", "gu": "Gujarati",
        "mr": "Marathi", "pa": "Punjabi", "or": "Oriya", "as": "Assamese",
        "ur": "Urdu", "sa": "Sanskrit", "ks": "Kashmiri", "ne": "Nepali",
        "sd": "Sindhi", "kok": "Konkani", "doi": "Dogri", "mai": "Maithili",
        "brx": "Bodo", "mni": "Manipuri", "sat": "Santali", "gom": "Goan Konkani",
        "fr": "French", "es": "Spanish", "de": "German", "it": "Italian",
        "pt": "Portuguese", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
        "zh": "Chinese", "ar": "Arabic", "th": "Thai", "vi": "Vietnamese"
    }
    
    # Extract input text, language configuration, and required context
    nmt_config = body_dict.get("config") or {}
    if not isinstance(nmt_config, dict):
        logger.error(
            "SMR: config is not a dict in context-aware request",
            extra={
                "context": {
                    "body_dict_keys": list(body_dict.keys()),
                    "config_type": type(nmt_config).__name__,
                    "config_value": str(nmt_config)[:200],
                }
            }
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CONFIG",
                "message": "config must be an object when X-Context-Aware is true"
            }
        )
    
    # When context-aware routing is enabled, config.context is required
    # Check if context exists and is not None/empty
    context_value = nmt_config.get("context")
    if not context_value:
        logger.error(
            "SMR: context is missing or empty in context-aware request",
            extra={
                "context": {
                    "nmt_config_keys": list(nmt_config.keys()),
                    "nmt_config": str(nmt_config)[:500],
                    "body_dict": str(body_dict)[:500],
                }
            }
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONTEXT_REQUIRED",
                "message": "config.context is required when X-Context-Aware is true. Please provide a non-empty context value in config.context."
            }
        )
    
    lang_cfg = nmt_config.get("language") or {}
    source_lang_code = lang_cfg.get("sourceLanguage", "en")
    target_lang_code = lang_cfg.get("targetLanguage", "en")
    
    # Map language codes to full names
    source_language = LANGUAGE_CODE_TO_NAME.get(source_lang_code, source_lang_code.capitalize())
    target_language = LANGUAGE_CODE_TO_NAME.get(target_lang_code, target_lang_code.capitalize())
    
    # Get input text (use first input if multiple)
    input_list = body_dict.get("input", [])
    if not input_list:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_INPUT",
                "message": "Input text is required"
            }
        )
    
    # Combine all input texts or use first one
    text = " ".join([item.get("source", "") for item in input_list if item.get("source")])
    if not text:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_INPUT",
                "message": "Source text cannot be empty"
            }
        )
    
    # Prepare translate API request (include context from config)
    translate_payload = {
        "text": text,
        "source_language": source_language,
        "target_language": target_language,
        "context": context_value,
    }
    
    logger.info(
        "SMR: Calling LLM translate API for context-aware NMT",
        extra={
            "context": {
                "source_language": source_language,
                "target_language": target_language,
                "text_length": len(text),
            }
        }
    )
    
    # Call translate API directly
    # Use environment variable for translate API URL, fallback to default
    translate_api_url = os.getenv("LLM_TRANSLATE_API_URL")
    if not translate_api_url:
        raise ValueError("LLM_TRANSLATE_API_URL environment variable is not set")
    try:
        translate_response = await http_client.post(
            translate_api_url,
            json=translate_payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0
        )
        
        translate_response.raise_for_status()
        translate_result = translate_response.json()
        
        # Extract translated text from response
        translated_text = None
        
        # Try common response field names
        if "translated_text" in translate_result and translate_result.get("translated_text"):
            translated_text = str(translate_result["translated_text"])
        elif "translation" in translate_result and translate_result.get("translation"):
            translated_text = str(translate_result["translation"])
        elif "result" in translate_result and translate_result.get("result"):
            translated_text = str(translate_result["result"])
        elif "text" in translate_result and translate_result.get("text"):
            translated_text = str(translate_result["text"])
        elif "output" in translate_result and translate_result.get("output"):
            translated_text = str(translate_result["output"])
        elif isinstance(translate_result, str):
            translated_text = translate_result
        
        if not translated_text:
            logger.warning(
                "Translate API response format unexpected",
                extra={"context": {"response": translate_result}}
            )
            translated_text = "Translation unavailable"
        
        # Format response in NMT format
        output_list = []
        for item in input_list:
            output_list.append({
                "source": item.get("source", ""),
                "target": translated_text  # Use same translation for all inputs
            })
        
        return {"output": output_list}
        
    except httpx.HTTPStatusError as e:
        logger.error(
            "SMR: Translate API returned error",
            extra={
                "context": {
                    "status_code": e.response.status_code,
                    "response_text": e.response.text[:500] if e.response else None,
                }
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=e.response.status_code if e.response else 500,
            detail={
                "code": "TRANSLATE_API_ERROR",
                "message": f"Translation service error: {e.response.text[:200] if e.response else str(e)}",
            },
        )
    except httpx.RequestError as e:
        logger.error(
            "SMR: Translate API connection error",
            extra={"context": {"error": str(e)}},
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "TRANSLATE_API_UNAVAILABLE",
                "message": "Translation service is temporarily unavailable. Please try again later.",
            },
        )


async def inject_service_id_if_missing(
    http_client: httpx.AsyncClient,
    task_type: str,
    body_dict: Dict[str, Any],
    user_id: Optional[str],
    tenant_id: Optional[str],
    latency_policy: Optional[str] = None,
    cost_policy: Optional[str] = None,
    accuracy_policy: Optional[str] = None,
    is_context_aware: bool = False,
    is_request_profiler: bool = False,
    mm_headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Optional[str], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Ensure that body_dict.config.serviceId is populated, using SMR selection if needed.
    
    For context-aware requests:
    - If task_type is "nmt", calls LLM translate API directly and returns result
    - If task_type is not "nmt", returns error that context-aware is only available for NMT
    
    For request profiler requests:
    - If task_type is "nmt" or "tts", calls request profiler service and selects best matching service
    - If task_type is not "nmt" or "tts", returns error that profiler is only available for NMT and TTS

    Returns (service_id, fallback_service_id, updated_body_dict, tenant_policy_result, selected_service_dict, scoring_details, context_aware_result).
    """
    # Handle request profiler requests (only for NMT)
    # IMPORTANT: This check must happen FIRST, before any other routing logic
    logger.info(
        "SMR: inject_service_id_if_missing - checking profiler flag",
        extra={
            "context": {
                "is_request_profiler": is_request_profiler,
                "task_type": task_type,
                "body_dict_keys": list(body_dict.keys()) if body_dict else [],
                "has_config": "config" in (body_dict or {}),
                "config_service_id": body_dict.get("config", {}).get("serviceId") if isinstance(body_dict.get("config"), dict) else None,
            }
        }
    )
    if is_request_profiler:
        # Allow request profiler for both NMT and TTS
        if task_type.lower() not in ("nmt", "tts"):
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "PROFILER_NOT_AVAILABLE",
                    "message": f"Request profiler feature is not available for {task_type.upper()} service. This feature is currently only available for NMT (Neural Machine Translation) and TTS (Text-to-Speech) services.",
                },
            )
        
        # Extract text from request (works for both NMT and TTS)
        # Both use input array with "source" field
        input_list = body_dict.get("input", [])
        if not input_list:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "Input text is required for profiler routing",
                },
            )
        
        # Combine all input texts
        text_parts = []
        for item in input_list:
            if isinstance(item, dict):
                source = item.get("source", "")
                if source:
                    text_parts.append(str(source))
            elif isinstance(item, str):
                text_parts.append(item)
        
        if not text_parts:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_INPUT",
                    "message": "Source text cannot be empty for profiler routing",
                },
            )
        
        combined_text = " ".join(text_parts)
        
        logger.info(
            f"SMR: Request profiler routing enabled for {task_type.upper()}",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "text_length": len(combined_text),
                }
            }
        )
        
        # Call request profiler service
        profiler_result = await call_request_profiler(http_client, combined_text)
        profiler_domain = profiler_result.get("domain")
        profiler_complexity = profiler_result.get("complexity_level")
        
        # Fetch candidate services (forward auth headers to model-management if available)
        candidate_services = await fetch_candidate_services_for_task(
            http_client=http_client,
            task_type=task_type,
            headers=mm_headers,
        )
        
        if not candidate_services:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "NO_CANDIDATE_SERVICES",
                    "message": "No candidate services found for the given task type.",
                },
            )
        
        # Select service based on profiler matching
        selected_service, fallback_service, scoring_details = await select_service_by_profiler(
            http_client=http_client,
            services=candidate_services,
            profiler_domain=profiler_domain,
            profiler_complexity=profiler_complexity,
            fetch_model_domain_fn=fetch_model_domain,
        )
        
        service_id = str(selected_service.get("serviceId"))
        fallback_service_id = str(fallback_service.get("serviceId")) if fallback_service else None
        
        config = body_dict.get("config") or {}
        if not isinstance(config, dict):
            config = {}
        config["serviceId"] = service_id
        body_dict["config"] = config
        
        logger.info(
            "SMR: Service selected by profiler routing",
            extra={
                "context": {
                    "selected_service_id": service_id,
                    "fallback_service_id": fallback_service_id,
                    "profiler_domain": profiler_domain,
                    "profiler_complexity": profiler_complexity,
                }
            }
        )
        
        return service_id, fallback_service_id, body_dict, None, selected_service, scoring_details, None
    
    # Handle context-aware requests
    if is_context_aware:
        if task_type.lower() != "nmt":
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "CONTEXT_AWARE_NOT_AVAILABLE",
                    "message": f"Context-aware feature is not available for {task_type.upper()} service. This feature is currently only available for NMT (Neural Machine Translation) service.",
                },
            )
        
        # For NMT, handle context-aware by calling LLM translate API
        logger.info(
            "SMR: Context-aware routing enabled for NMT, calling LLM translate API",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                }
            }
        )
        
        context_aware_result = await handle_context_aware_nmt(http_client, body_dict)
        
        # Return special serviceId to indicate context-aware was used
        # The context_aware_result will be included in the response
        return "llm_context_aware", None, body_dict, None, None, None, context_aware_result
    
    config = body_dict.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_CONFIG",
                "message": "request_body.config must be an object.",
            },
        )

    existing_service_id = config.get("serviceId")
    if existing_service_id:
        logger.info(
            "SMR: serviceId already present in request, skipping routing",
            extra={"context": {"service_id": str(existing_service_id), "task_type": task_type}},
        )
        return str(existing_service_id), None, body_dict, None, None, None, None

    headers_provided = (
        latency_policy is not None or cost_policy is not None or accuracy_policy is not None
    )

    policy_result: Optional[Dict[str, Any]] = None
    actual_latency_policy: Optional[str] = None
    actual_cost_policy: Optional[str] = None
    actual_accuracy_policy: Optional[str] = None

    # Priority 1: Headers have HIGHEST priority (as per flow diagram)
    # If headers are provided, use them directly for routing
    # But still call Policy Engine for observability (to show what tenant policy would be)
    if headers_provided:
        logger.info(
            "SMR: Using policy headers directly (highest priority for routing)",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "latency_policy": latency_policy,
                    "cost_policy": cost_policy,
                    "accuracy_policy": accuracy_policy,
                    "decision": "header_priority",
                }
            },
        )
        actual_latency_policy = latency_policy
        actual_cost_policy = cost_policy
        actual_accuracy_policy = accuracy_policy

        if actual_latency_policy and hasattr(actual_latency_policy, "value"):
            actual_latency_policy = actual_latency_policy.value
        if actual_cost_policy and hasattr(actual_cost_policy, "value"):
            actual_cost_policy = actual_cost_policy.value
        if actual_accuracy_policy and hasattr(actual_accuracy_policy, "value"):
            actual_accuracy_policy = actual_accuracy_policy.value

        # Headers take priority - skip Policy Engine call since headers are used for routing
        # tenant_policy will be None in response when headers are provided
        policy_result = None
        logger.info(
            "SMR: Headers provided, skipping Policy Engine call (headers used for routing)",
            extra={
                "context": {
                    "tenant_id": tenant_id,
                    "routing_decision": "headers_priority",
                }
            }
        )
    # Priority 2: No headers provided - call Policy Engine
    elif tenant_id is None or tenant_id == "" or tenant_id == "free-user":
        # Free user: call Policy Engine with tenant_id="free-user" to get policy from DB
        # Note: ObservabilityMiddleware may set tenant_id="free-user" for free users
        # Empty string "" is also treated as free user
        logger.info(
            "SMR: No policy headers provided, calling Policy Engine for free-user policy",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "decision": "policy_engine_free_user",
                }
            },
        )
        policy_result = await call_policy_engine_for_smr(
            http_client=http_client,
            user_id=user_id,
            tenant_id="free-user",  # Use "free-user" as tenant_id to lookup policy from DB
            latency_policy=None,
            cost_policy=None,
            accuracy_policy=None,
        )

        actual_latency_policy = policy_result.get("latency_policy")
        actual_cost_policy = policy_result.get("cost_policy")
        actual_accuracy_policy = policy_result.get("accuracy_policy")

        if actual_latency_policy and hasattr(actual_latency_policy, "value"):
            actual_latency_policy = actual_latency_policy.value
        if actual_cost_policy and hasattr(actual_cost_policy, "value"):
            actual_cost_policy = actual_cost_policy.value
        if actual_accuracy_policy and hasattr(actual_accuracy_policy, "value"):
            actual_accuracy_policy = actual_accuracy_policy.value
    else:
        # Tenant user: call Policy Engine with tenant_id to get tenant-specific policy
        logger.info(
            "SMR: No policy headers provided, calling Policy Engine for tenant policy",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "decision": "policy_engine_tenant",
                }
            },
        )
        policy_result = await call_policy_engine_for_smr(
            http_client=http_client,
            user_id=user_id,
            tenant_id=tenant_id,
            latency_policy=None,
            cost_policy=None,
            accuracy_policy=None,
        )

        actual_latency_policy = policy_result.get("latency_policy")
        actual_cost_policy = policy_result.get("cost_policy")
        actual_accuracy_policy = policy_result.get("accuracy_policy")

        if actual_latency_policy and hasattr(actual_latency_policy, "value"):
            actual_latency_policy = actual_latency_policy.value
        if actual_cost_policy and hasattr(actual_cost_policy, "value"):
            actual_cost_policy = actual_cost_policy.value
        if actual_accuracy_policy and hasattr(actual_accuracy_policy, "value"):
            actual_accuracy_policy = actual_accuracy_policy.value

    candidate_services = await fetch_candidate_services_for_task(
        http_client=http_client,
        task_type=task_type,
        headers=mm_headers,
    )

    try:
        policies_map = await fetch_policies_for_task(
            http_client=http_client,
            task_type=task_type,
            headers=mm_headers,
        )
        if policies_map:
            for svc in candidate_services:
                sid = str(svc.get("serviceId", ""))
                if not sid:
                    continue
                if svc.get("policy") in (None, {}):
                    policy = policies_map.get(sid)
                    if policy is not None:
                        svc["policy"] = policy
    except Exception as e:
        logger.warning(f"SMR: Failed to enrich services with policies: {e}")

    if not candidate_services:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_CANDIDATE_SERVICES",
                "message": "No candidate services found for the given task type.",
            },
        )

    # Validate policy combinations before service selection
    # Only validate when policies come from user-provided headers, not from Policy Engine
    # Policy Engine should return valid combinations, but if it doesn't, we'll handle it gracefully
    # Invalid combinations: sensitive accuracy with Tier 1 cost, Low latency with Tier 1 cost
    # Check if policies came from headers (user-provided) vs Policy Engine
    policies_from_headers = (latency_policy is not None or cost_policy is not None or accuracy_policy is not None)
    if policies_from_headers:
        # Only validate user-provided policies
        validate_policy_combinations(
            latency_policy=actual_latency_policy,
            cost_policy=actual_cost_policy,
            accuracy_policy=actual_accuracy_policy,
        )
    else:
        # Policies came from Policy Engine - log warning if invalid but don't fail
        # This allows Policy Engine to return policies that may not be strictly valid
        # but we'll still try to route (the service selection will handle it)
        cost_policy_lower = str(actual_cost_policy).lower() if actual_cost_policy else None
        if cost_policy_lower == "tier_1":
            if actual_accuracy_policy and str(actual_accuracy_policy).lower() == "sensitive":
                logger.warning(
                    "Policy Engine returned invalid combination: sensitive accuracy with Tier 1 cost. "
                    "This may result in suboptimal routing.",
                    extra={
                        "context": {
                            "latency_policy": actual_latency_policy,
                            "cost_policy": actual_cost_policy,
                            "accuracy_policy": actual_accuracy_policy,
                            "source": "policy_engine",
                        }
                    }
                )
            if actual_latency_policy and str(actual_latency_policy).lower() == "low":
                logger.warning(
                    "Policy Engine returned invalid combination: low latency with Tier 1 cost. "
                    "This may result in suboptimal routing.",
                    extra={
                        "context": {
                            "latency_policy": actual_latency_policy,
                            "cost_policy": actual_cost_policy,
                            "accuracy_policy": actual_accuracy_policy,
                            "source": "policy_engine",
                        }
                    }
                )

    # Log candidate services for debugging
    logger.info(
        "SMR: Selecting from candidate services",
        extra={
            "context": {
                "task_type": task_type,
                "candidate_count": len(candidate_services),
                "latency_policy": actual_latency_policy,
                "cost_policy": actual_cost_policy,
                "accuracy_policy": actual_accuracy_policy,
                "candidate_service_ids": [str(s.get("serviceId", "")) for s in candidate_services[:10]],  # First 10
            }
        },
    )
    
    selected_service, fallback_service, scoring_details = select_service_deterministically(
        candidate_services,
        preferred_language=None,
        latency_policy=actual_latency_policy,
        cost_policy=actual_cost_policy,
        accuracy_policy=actual_accuracy_policy,
    )
    service_id = str(selected_service.get("serviceId"))
    fallback_service_id = str(fallback_service.get("serviceId")) if fallback_service else None
    
    # Log selection details
    logger.info(
        "SMR: Service selected with scoring details",
        extra={
            "context": {
                "selected_service_id": service_id,
                "fallback_service_id": fallback_service_id,
                "tie_level": scoring_details.get("tie_level", 0),
                "tie_breaker_level": scoring_details.get("tie_breaker_level", {}),
            }
        },
    )

    logger.info(
        "SMR: Selected service for routing",
        extra={
            "context": {
                "task_type": task_type,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "selected_service_id": service_id,
                "fallback_service_id": fallback_service_id,
            }
        },
    )

    config["serviceId"] = service_id
    body_dict["config"] = config

    return service_id, fallback_service_id, body_dict, policy_result, selected_service, scoring_details, None


@app.post("/api/v1/smr/select-service", response_model=SMRSelectResponse)
async def select_service(request: Request, payload: SMRSelectRequest) -> SMRSelectResponse:
    """
    Select the best serviceId for a given task_type and inference payload.

    This endpoint:
    - Reads policy headers from the HTTP request (if any)
    - Uses provided user_id / tenant_id (so callers can reuse their auth context)
    - Calls existing SMR core logic to choose a serviceId
    - Returns only the chosen serviceId (+ optional policy metadata), without proxying downstream
    """
    # Extract headers from the incoming request
    headers = dict(request.headers)
    
    # Log all headers for debugging
    logger.info(
        "SMR: Received request headers",
        extra={
            "all_header_keys": list(headers.keys()),
            "x_headers": {k: v for k, v in headers.items() if k.startswith("X-") or k.startswith("x-")},
        }
    )

    # Build a mutable copy of the inference body for SMR core
    body_dict = dict(payload.request_body or {})

    # Extract user context
    user_id = payload.user_id
    tenant_id = payload.tenant_id

    # Prepare auth-related headers to forward to model-management-service.
    # Model Management's AuthProvider expects:
    # - Authorization (Bearer <token>) and X-Auth-Source=AUTH_TOKEN for JWT-based auth
    # - or X-API-Key / Authorization (ApiKey <key>) with X-Auth-Source=API_KEY for API key auth
    lower_headers = {k.lower(): v for k, v in headers.items()}
    mm_headers: Dict[str, str] = {}
    if "authorization" in lower_headers:
        mm_headers["Authorization"] = lower_headers["authorization"]
    if "x-api-key" in lower_headers:
        mm_headers["X-API-Key"] = lower_headers["x-api-key"]
    if "x-auth-source" in lower_headers:
        mm_headers["X-Auth-Source"] = lower_headers["x-auth-source"]
    # Forward X-Try-It so anonymous "try-it" flows work consistently if enabled
    if "x-try-it" in lower_headers:
        mm_headers["X-Try-It"] = lower_headers["x-try-it"]
    
    # Extract policy headers (highest priority) - these override Policy Engine
    # Headers: X-Latency-Policy, X-Cost-Policy, X-Accuracy-Policy
    latency_policy_header = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
    cost_policy_header = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
    accuracy_policy_header = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")
    
    # Check if request profiler is enabled (from header)
    # Check both case variations of the header name
    request_profiler_header = (
        headers.get("X-Request-Profiler") or 
        headers.get("x-request-profiler") or
        headers.get("X-Request-Profiler".lower())
    )
    is_request_profiler = False
    if request_profiler_header:
        header_value = str(request_profiler_header).strip().lower()
        is_request_profiler = header_value in ("true", "1", "yes", "y")
        logger.info(
            "SMR: Request profiler header found",
            extra={
                "context": {
                    "request_profiler_header": request_profiler_header,
                    "header_value": header_value,
                    "is_request_profiler": is_request_profiler,
                }
            }
        )
    else:
        logger.info(
            "SMR: No request profiler header found",
            extra={
                "context": {
                    "all_headers_keys": list(headers.keys()),
                    "profiler_headers": {k: v for k, v in headers.items() if "profiler" in k.lower()},
                }
            }
        )
    
    # Check if context-aware (from header or request body)
    is_context_aware = (
        headers.get("X-Context-Aware", "").lower() == "true" or
        headers.get("x-context-aware", "").lower() == "true" or
        body_dict.get("context_aware", False) is True
    )
    
    # Validate that only one routing mode can be used at a time.
    # Policy headers (X-Latency-Policy, X-Cost-Policy, X-Accuracy-Policy) are all part of the
    # same "policy" mode and can be combined freely; they count as a single feature.
    has_policy_headers = bool(latency_policy_header or cost_policy_header or accuracy_policy_header)
    feature_headers_count = sum([
        is_request_profiler,
        is_context_aware,
        has_policy_headers,
    ])
    
    if feature_headers_count > 1:
        used_features = []
        if is_request_profiler:
            used_features.append("X-Request-Profiler")
        if is_context_aware:
            used_features.append("X-Context-Aware")
        if has_policy_headers:
            policy_headers_used = []
            if latency_policy_header:
                policy_headers_used.append("X-Latency-Policy")
            if cost_policy_header:
                policy_headers_used.append("X-Cost-Policy")
            if accuracy_policy_header:
                policy_headers_used.append("X-Accuracy-Policy")
            used_features.append(f"Policy headers ({', '.join(policy_headers_used)})")
        
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MULTIPLE_FEATURES_NOT_ALLOWED",
                "message": f"Only one feature header can be used at a time. You have provided: {', '.join(used_features)}. Please use only one feature header per request.",
                "provided_features": used_features,
            },
        )

    # Reuse a short‑lived httpx client for the SMR core helpers
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        try:
            # Log before calling inject_service_id_if_missing to verify flags
            logger.info(
                "SMR: Calling inject_service_id_if_missing",
                extra={
                    "context": {
                        "is_request_profiler": is_request_profiler,
                        "is_context_aware": is_context_aware,
                        "task_type": payload.task_type,
                        "has_latency_policy": bool(latency_policy_header),
                        "has_cost_policy": bool(cost_policy_header),
                        "has_accuracy_policy": bool(accuracy_policy_header),
                    }
                }
            )
            service_id, fallback_service_id, updated_body, tenant_policy_result, selected_service, scoring_details, context_aware_result = await inject_service_id_if_missing(
                http_client=http_client,
                task_type=payload.task_type,
                body_dict=body_dict,
                user_id=user_id,
                tenant_id=tenant_id,
                latency_policy=latency_policy_header,
                cost_policy=cost_policy_header,
                accuracy_policy=accuracy_policy_header,
                is_context_aware=is_context_aware,
                is_request_profiler=is_request_profiler,
                mm_headers=mm_headers or None,
            )
            # Log after calling to verify what was returned
            logger.info(
                "SMR: inject_service_id_if_missing returned",
                extra={
                    "context": {
                        "service_id": service_id,
                        "has_scoring_details": bool(scoring_details),
                        "scoring_details_keys": list(scoring_details.keys()) if scoring_details else [],
                        "has_profiler_domain": bool(scoring_details.get("profiler_domain") if scoring_details else False),
                        "has_profiler_complexity": bool(scoring_details.get("profiler_complexity") if scoring_details else False),
                    }
                }
            )
        except HTTPException:
            # Bubble up FastAPI HTTPExceptions as‑is
            raise
        except Exception as e:
            # Wrap unexpected errors
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "SMR_INTERNAL_ERROR",
                    "message": f"Smart Model Router failed to select service: {e}",
                },
            )

    # Extract tenant_policy from Policy Engine result (tenant requirements)
    # Only include tenant_policy if it's from DB (policy_id="tenant_db_policy"), not from defaults
    tenant_policy_dict = None
    if tenant_policy_result:
        policy_id = tenant_policy_result.get("policy_id", "")
        # Only return tenant_policy if it's from DB, not from defaults or free-user
        if policy_id == "tenant_db_policy":
            tenant_policy_dict = {
                "latency_policy": tenant_policy_result.get("latency_policy"),
                "cost_policy": tenant_policy_result.get("cost_policy"),
                "accuracy_policy": tenant_policy_result.get("accuracy_policy"),
            }
            # Only include if at least one policy value is present
            if not any(tenant_policy_dict.values()):
                tenant_policy_dict = None
        else:
            # Policy is from defaults (tenant_default_policy, default_policy, free-user defaults, etc.)
            # Don't include in response - tenant doesn't have a configured policy
            logger.debug(
                "SMR: Not including tenant_policy in response (policy is from defaults, not DB)",
                extra={
                    "policy_id": policy_id,
                    "tenant_id": tenant_id,
                }
            )

    # Extract service_policy from selected service (service characteristics from Model Management)
    service_policy_dict = None
    if selected_service:
        service_policy = selected_service.get("policy")
        if service_policy and isinstance(service_policy, dict):
            # Service policy may use "latency"/"cost"/"accuracy" or "latency_policy"/"cost_policy"/"accuracy_policy"
            # Normalize to consistent key names
            service_policy_dict = {
                "latency_policy": service_policy.get("latency_policy") or service_policy.get("latency"),
                "cost_policy": service_policy.get("cost_policy") or service_policy.get("cost"),
                "accuracy_policy": service_policy.get("accuracy_policy") or service_policy.get("accuracy"),
            }
            # Add domain and complexity from service policy if available
            if service_policy.get("domain"):
                service_policy_dict["domain"] = service_policy.get("domain")
            if service_policy.get("complexity"):
                service_policy_dict["complexity"] = service_policy.get("complexity")
            # Only include if at least one policy value is present
            if not any(service_policy_dict.values()):
                service_policy_dict = None
    
    # Extract request_profiler results from scoring_details (if profiler was used)
    request_profiler_dict = None
    if is_request_profiler and scoring_details:
        profiler_domain = scoring_details.get("profiler_domain")
        profiler_complexity = scoring_details.get("profiler_complexity")
        logger.info(
            "SMR: Extracting profiler results from scoring_details",
            extra={
                "context": {
                    "is_request_profiler": is_request_profiler,
                    "has_scoring_details": bool(scoring_details),
                    "scoring_details_keys": list(scoring_details.keys()) if scoring_details else [],
                    "profiler_domain": profiler_domain,
                    "profiler_complexity": profiler_complexity,
                }
            }
        )
        if profiler_domain or profiler_complexity:
            request_profiler_dict = {
                "domain": profiler_domain or "",
                "complexity": profiler_complexity or "",
            }
        else:
            logger.warning(
                "SMR: Request profiler was enabled but scoring_details doesn't contain profiler_domain or profiler_complexity",
                extra={
                    "context": {
                        "scoring_details": scoring_details,
                    }
                }
            )
    
    # Determine tenant_id and is_free_user
    # ObservabilityMiddleware may set tenant_id="free-user" for free users (when JWT has no tenant_id)
    # We treat None, empty string, and "free-user" as free users
    # In the response, we return null for free users (not "free-user")
    is_free_user = (tenant_id is None or tenant_id == "" or tenant_id == "free-user")
    # Return null for free users, actual tenant_id for tenant users
    # "free-user" is only used internally for Policy Engine lookup, not exposed in response
    actual_tenant_id = None if is_free_user else tenant_id
    
    return SMRSelectResponse(
        serviceId=service_id,
        fallbackServiceId=fallback_service_id,
        tenant_id=actual_tenant_id,  # null for free users, actual tenant_id for tenant users
        is_free_user=is_free_user,
        tenant_policy=tenant_policy_dict,
        service_policy=service_policy_dict,
        scoring_details=scoring_details,
        context_aware_result=context_aware_result,
        request_profiler=request_profiler_dict,
    )


def get_app() -> FastAPI:
    """Uvicorn entrypoint helper (for consistency with other services)."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.smr-service.main:get_app",  # type: ignore
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8097")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )

