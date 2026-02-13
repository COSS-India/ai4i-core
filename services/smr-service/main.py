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
) -> List[Dict[str, Any]]:
    """Fetch candidate services for a given task type from model-management-service."""
    params = {
        "task_type": task_type,
        "is_published": True,  # Send as boolean, not string
    }

    logger.info(
        "SMR: Fetching candidate services from model-management",
        extra={"context": {"task_type": task_type}},
    )
    try:
        resp = await http_client.get(
            f"{MODEL_MANAGEMENT_SERVICE_URL}/api/v1/model-management/services",
            params=params,
            timeout=15.0,
        )
    except httpx.RequestError as e:
        logger.error(f"Model Management request failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_MANAGEMENT_UNAVAILABLE",
                "message": "Model Management is temporarily unavailable. Please try again.",
            },
        )

    if resp.status_code != 200:
        error_body = resp.text[:500] if resp.text else "No response body"
        logger.error(
            "Model Management returned non-200 status",
            extra={
                "status_code": resp.status_code,
                "body": error_body,
                "url": f"{MODEL_MANAGEMENT_SERVICE_URL}/api/v1/model-management/services",
                "params": params,
            },
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "code": "MODEL_MANAGEMENT_ERROR",
                "message": f"Failed to fetch candidate services for routing. Status: {resp.status_code}, Response: {error_body}",
            },
        )

    data = resp.json()
    if not isinstance(data, list):
        logger.error("Unexpected response format from model-management (expected list)")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "MODEL_MANAGEMENT_BAD_RESPONSE",
                "message": "Model Management returned invalid response format.",
            },
        )

    return data


async def fetch_policies_for_task(
    http_client: httpx.AsyncClient,
    task_type: str,
) -> Dict[str, Dict[str, Any]]:
    """Fetch per-service policies for a given task type from model-management-service."""
    params = {"task_type": task_type}

    try:
        resp = await http_client.get(
            f"{MODEL_MANAGEMENT_SERVICE_URL}/api/v1/model-management/services/policies",
            params=params,
            timeout=10.0,
        )
    except httpx.RequestError as e:
        logger.warning(f"Model Management policy request failed: {e}")
        return {}

    if resp.status_code != 200:
        logger.warning(
            "Model Management returned non-200 status for policies",
            extra={"status_code": resp.status_code, "body": resp.text},
        )
        return {}

    payload = resp.json()
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, list):
        logger.warning("Unexpected policy response format from model-management")
        return {}

    policies_map: Dict[str, Dict[str, Any]] = {}
    for entry in services:
        try:
            sid = entry.get("serviceId")
            pol = entry.get("policy")
            if sid and isinstance(pol, dict):
                policies_map[str(sid)] = pol
        except AttributeError:
            continue

    logger.info(
        "SMR: Loaded service policies",
        extra={
            "context": {
                "task_type": task_type,
                "policy_count": len(policies_map),
            }
        },
    )
    return policies_map


def _compute_latency_score_for_service(
    svc: Dict[str, Any],
    preferred_language: Optional[str],
) -> Optional[int]:
    """
    Compute a latency score for a service based on its benchmarks.
    Returns positive integer score (higher is better).
    Lower latency (ms) = higher score. Score = 10000 / (latency_ms + 1)
    """
    benchmarks = svc.get("benchmarks") or {}
    if not isinstance(benchmarks, dict):
        return None

    latencies: List[int] = []

    # First pass: prefer entries with matching language
    for entries in benchmarks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if preferred_language and entry.get("language") != preferred_language:
                continue
            try:
                p50 = entry.get("50%")
                if p50 is not None:
                    latencies.append(int(p50))
            except Exception:
                continue

    # Second pass: any language if nothing found
    if not latencies:
        for entries in benchmarks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                try:
                    p50 = entry.get("50%")
                    if p50 is not None:
                        latencies.append(int(p50))
                except Exception:
                    continue

    if not latencies:
        return None
    
    # Convert latency (lower is better) to positive score (higher is better)
    # Use formula: score = 10000 / (latency_ms + 1)
    # This gives higher scores for lower latencies
    min_latency = min(latencies)
    score = 10000 // (min_latency + 1)
    return score


def _get_cost_tier_value(service_policy: Optional[Dict[str, Any]]) -> int:
    """Extract cost tier value from service policy for sorting."""
    if not service_policy or not isinstance(service_policy, dict):
        return 999

    cost = service_policy.get("cost")
    if not cost:
        return 999

    cost_str = str(cost).lower()
    if cost_str == "tier_1":
        return 1
    if cost_str == "tier_2":
        return 2
    if cost_str == "tier_3":
        return 3
    return 999


def _compute_policy_match_score_for_service(
    svc: Dict[str, Any],
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str],
) -> Optional[int]:
    """
    Compute how well a service matches the requested latency/cost/accuracy policy.
    Returns positive integer score (higher is better, max 3 for perfect match).
    """
    if not (latency_policy or cost_policy or accuracy_policy):
        return None

    score = 0
    max_score = 0
    service_policy = svc.get("policy")
    if service_policy and isinstance(service_policy, dict):
        # Check both "latency" and "latency_policy" keys (policy may use either)
        service_latency = (
            str(service_policy.get("latency_policy") or service_policy.get("latency", "")).lower()
            if (service_policy.get("latency_policy") or service_policy.get("latency"))
            else None
        )
        # Check both "cost" and "cost_policy" keys
        service_cost = (
            str(service_policy.get("cost_policy") or service_policy.get("cost", "")).lower()
            if (service_policy.get("cost_policy") or service_policy.get("cost"))
            else None
        )
        # Check both "accuracy" and "accuracy_policy" keys
        service_accuracy = (
            str(service_policy.get("accuracy_policy") or service_policy.get("accuracy", "")).lower()
            if (service_policy.get("accuracy_policy") or service_policy.get("accuracy"))
            else None
        )

        if latency_policy:
            max_score += 1
            lp = str(latency_policy).lower()
            if service_latency and service_latency == lp:
                score += 1

        if cost_policy:
            max_score += 1
            cp = str(cost_policy).lower()
            if service_cost and service_cost == cp:
                score += 1

        if accuracy_policy:
            max_score += 1
            ap = str(accuracy_policy).lower()
            if service_accuracy and service_accuracy == ap:
                score += 1

        return score

    desc = str(svc.get("serviceDescription") or "").lower()
    if not desc:
        return None

    if latency_policy:
        max_score += 1
        lp = str(latency_policy).lower()
        if lp == "low" and "low latency" in desc:
            score += 1
        elif lp == "medium" and "medium latency" in desc:
            score += 1
        elif lp == "high" and "high latency" in desc:
            score += 1

    if cost_policy:
        max_score += 1
        cp = str(cost_policy).lower()
        if cp.startswith("tier_1") and "tier_1 cost" in desc:
            score += 1
        elif cp.startswith("tier_2") and "tier_2 cost" in desc:
            score += 1
        elif cp.startswith("tier_3") and "tier_3 cost" in desc:
            score += 1

    if accuracy_policy:
        max_score += 1
        ap = str(accuracy_policy).lower()
        if ap == "sensitive" and "sensitive accuracy" in desc:
            score += 1
        elif ap == "standard" and "standard accuracy" in desc:
            score += 1

    return score


def validate_policy_combinations(
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str],
) -> None:
    """
    Validate policy combinations and raise HTTPException for invalid combinations.
    
    Invalid combinations:
    - sensitive accuracy with Tier 1 cost
    - Low latency with Tier 1 cost
    """
    if not cost_policy:
        return  # No cost policy specified, skip validation
    
    cost_policy_lower = str(cost_policy).lower() if cost_policy else None
    
    # Check for invalid combinations
    if cost_policy_lower == "tier_1":
        if accuracy_policy and str(accuracy_policy).lower() == "sensitive":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_POLICY_COMBINATION",
                    "message": "Invalid policy combination: sensitive accuracy cannot be used with Tier 1 cost. Sensitive accuracy requires higher cost tiers (Tier 2 or Tier 3).",
                    "invalid_combination": {
                        "accuracy_policy": accuracy_policy,
                        "cost_policy": cost_policy,
                    }
                },
            )
        
        if latency_policy and str(latency_policy).lower() == "low":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_POLICY_COMBINATION",
                    "message": "Invalid policy combination: low latency cannot be used with Tier 1 cost. Low latency requires higher cost tiers (Tier 2 or Tier 3).",
                    "invalid_combination": {
                        "latency_policy": latency_policy,
                        "cost_policy": cost_policy,
                    }
                },
            )


def select_service_deterministically(
    services: List[Dict[str, Any]],
    preferred_language: Optional[str],
    latency_policy: Optional[str] = None,
    cost_policy: Optional[str] = None,
    accuracy_policy: Optional[str] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Deterministically select the best service from candidates.
    Returns (selected_service, scoring_details).
    """
    if not services:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_SERVICES_AVAILABLE",
                "message": "No candidate services available for routing.",
            },
        )

    policy_scored: List[Tuple[int, str, Dict[str, Any]]] = []
    scored: List[Tuple[int, str, Dict[str, Any]]] = []
    fallback: List[Tuple[str, Dict[str, Any]]] = []

    for svc in services:
        if svc.get("isPublished") is False:
            continue

        health = svc.get("healthStatus") or {}
        if isinstance(health, dict):
            status = str(health.get("status", "")).lower()
            if status and status not in ("healthy", "up"):
                continue

        service_id = str(svc.get("serviceId", ""))
        if not service_id:
            continue

        policy_score = _compute_policy_match_score_for_service(
            svc,
            latency_policy=latency_policy,
            cost_policy=cost_policy,
            accuracy_policy=accuracy_policy,
        )
        if policy_score is not None:
            policy_scored.append((policy_score, service_id, svc))
            # Log policy score for debugging tie detection
            logger.info(
                "SMR: Service has policy score",
                extra={
                    "service_id": service_id,
                    "policy_score": policy_score,
                    "service_policy": svc.get("policy"),
                    "latency_policy": latency_policy,
                    "cost_policy": cost_policy,
                    "accuracy_policy": accuracy_policy,
                }
            )
            continue

        latency_score = _compute_latency_score_for_service(svc, preferred_language)
        if latency_score is not None:
            scored.append((latency_score, service_id, svc))
        else:
            fallback.append((service_id, svc))

    scoring_details: Dict[str, Any] = {
        "tie_level": 0,
        "tie_breaker_level": {
            "first": None,
            "second": None,
        }
    }

    # Sort in descending order (higher score is better) for policy_scored and scored
    # Sort in ascending order for fallback (lower cost tier is better)
    if policy_scored:
        # Sort by score (desc), then cost tier (asc), then service_id (asc)
        policy_scored.sort(
            key=lambda x: (
                -x[0],  # Negative for descending order
                _get_cost_tier_value(x[2].get("policy")),
                x[1],
            )
        )
        selected = policy_scored[0][2]
        
        # Check for ties at policy score level
        # We check BEFORE considering cost_tier, so we can detect if multiple services
        # have the same policy score (even if they have different cost tiers)
        top_score = policy_scored[0][0]
        tied_services = [x for x in policy_scored if x[0] == top_score]
        
        # Log all services with their scores for debugging
        logger.info(
            "SMR: Checking for ties in policy_scored",
            extra={
                "total_services": len(policy_scored),
                "top_score": top_score,
                "tied_count": len(tied_services),
                "tied_service_ids": [x[1] for x in tied_services],
                "all_scores": [{"service_id": x[1], "score": x[0], "cost_tier": _get_cost_tier_value(x[2].get("policy"))} for x in policy_scored[:10]],  # First 10
            }
        )
        
        if len(tied_services) > 1:
            # There is a tie at policy score level
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
            
            # Check if tie was broken by cost tier
            top_cost_tier = _get_cost_tier_value(tied_services[0][2].get("policy"))
            cost_tied = [x for x in tied_services if _get_cost_tier_value(x[2].get("policy")) == top_cost_tier]
            
            logger.info(
                "SMR: Tie detected, checking cost tier break",
                extra={
                    "tied_count": len(tied_services),
                    "top_cost_tier": top_cost_tier,
                    "cost_tied_count": len(cost_tied),
                    "tied_service_ids": [x[1] for x in tied_services],
                }
            )
            
            if len(cost_tied) > 1:
                # Tie still exists after cost tier - broken by lexicographic order
                scoring_details["tie_level"] = 2
                scoring_details["tie_breaker_level"]["second"] = "lexicographic_order"
            else:
                # Tie was broken by cost tier (already set first = "lowest_cost")
                scoring_details["tie_breaker_level"]["second"] = None
        else:
            # No tie at policy score level - selection was unambiguous
            # Don't populate tie_breaker_level when there's no tie
            scoring_details["tie_breaker_level"]["first"] = None
            scoring_details["tie_breaker_level"]["second"] = None
        
        return selected, scoring_details

    if scored:
        scored.sort(
            key=lambda x: (
                -x[0],  # Negative for descending order
                _get_cost_tier_value(x[2].get("policy")),
                x[1],
            )
        )
        selected = scored[0][2]
        
        # Check for ties at latency score level
        top_score = scored[0][0]
        tied_services = [x for x in scored if x[0] == top_score]
        
        logger.debug(
            "SMR: Checking for ties in scored (latency-based)",
            extra={
                "total_services": len(scored),
                "top_score": top_score,
                "tied_count": len(tied_services),
                "tied_service_ids": [x[1] for x in tied_services],
            }
        )
        
        if len(tied_services) > 1:
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
            top_cost_tier = _get_cost_tier_value(tied_services[0][2].get("policy"))
            cost_tied = [x for x in tied_services if _get_cost_tier_value(x[2].get("policy")) == top_cost_tier]
            if len(cost_tied) > 1:
                scoring_details["tie_level"] = 2
                scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
                scoring_details["tie_breaker_level"]["second"] = "lexicographic_order"
            else:
                # Tie was broken by cost tier
                scoring_details["tie_breaker_level"]["second"] = None
        else:
            # No tie - don't populate tie_breaker_level
            scoring_details["tie_breaker_level"]["first"] = None
            scoring_details["tie_breaker_level"]["second"] = None
        
        return selected, scoring_details

    if fallback:
        fallback.sort(
            key=lambda x: (
                _get_cost_tier_value(x[1].get("policy")),
                x[0],
            )
        )
        selected = fallback[0][1]
        
        # Check for ties in fallback (by cost tier)
        top_cost_tier = _get_cost_tier_value(fallback[0][1].get("policy"))
        cost_tied = [x for x in fallback if _get_cost_tier_value(x[1].get("policy")) == top_cost_tier]
        if len(cost_tied) > 1:
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
            scoring_details["tie_breaker_level"]["second"] = "lexicographic_order"
        else:
            # No tie - don't populate tie_breaker_level
            scoring_details["tie_breaker_level"]["first"] = None
            scoring_details["tie_breaker_level"]["second"] = None
        
        return selected, scoring_details

    raise HTTPException(
        status_code=503,
        detail={
            "code": "NO_HEALTHY_SERVICES",
            "message": "No healthy services available for routing.",
        },
    )


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
    translate_api_url = os.getenv("LLM_TRANSLATE_API_URL", "http://13.201.75.118:8000/api/translate")
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
) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Ensure that body_dict.config.serviceId is populated, using SMR selection if needed.
    
    For context-aware requests:
    - If task_type is "nmt", calls LLM translate API directly and returns result
    - If task_type is not "nmt", returns error that context-aware is only available for NMT

    Returns (service_id, updated_body_dict, tenant_policy_result, selected_service_dict, scoring_details, context_aware_result).
    """
    # Handle context-aware requests
    if is_context_aware:
        if task_type.lower() != "nmt":
            raise HTTPException(
                status_code=501,
                detail={
                    "code": "CONTEXT_AWARE_NOT_AVAILABLE",
                    "message": f"Context-aware routing is currently only available for NMT (Neural Machine Translation) inference. This feature for {task_type.upper()} is under development and will be available in a future release.",
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
        return "llm_context_aware", body_dict, None, None, None, context_aware_result
    
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
        return str(existing_service_id), body_dict, None, None, None, None

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
    )

    try:
        policies_map = await fetch_policies_for_task(http_client, task_type)
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
    
    selected_service, scoring_details = select_service_deterministically(
        candidate_services,
        preferred_language=None,
        latency_policy=actual_latency_policy,
        cost_policy=actual_cost_policy,
        accuracy_policy=actual_accuracy_policy,
    )
    service_id = str(selected_service.get("serviceId"))
    
    # Log selection details
    logger.info(
        "SMR: Service selected with scoring details",
        extra={
            "context": {
                "selected_service_id": service_id,
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
            }
        },
    )

    config["serviceId"] = service_id
    body_dict["config"] = config

    return service_id, body_dict, policy_result, selected_service, scoring_details, None


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

    # Build a mutable copy of the inference body for SMR core
    body_dict = dict(payload.request_body or {})

    # Extract user context
    user_id = payload.user_id
    tenant_id = payload.tenant_id
    
    # Extract policy headers (highest priority) - these override Policy Engine
    # Headers: X-Latency-Policy, X-Cost-Policy, X-Accuracy-Policy
    latency_policy_header = headers.get("X-Latency-Policy") or headers.get("x-latency-policy")
    cost_policy_header = headers.get("X-Cost-Policy") or headers.get("x-cost-policy")
    accuracy_policy_header = headers.get("X-Accuracy-Policy") or headers.get("x-accuracy-policy")
    
    # Check if context-aware (from header or request body)
    is_context_aware = (
        headers.get("X-Context-Aware", "").lower() == "true" or
        headers.get("x-context-aware", "").lower() == "true" or
        body_dict.get("context_aware", False) is True
    )

    # Reuse a short‑lived httpx client for the SMR core helpers
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        try:
            service_id, updated_body, tenant_policy_result, selected_service, scoring_details, context_aware_result = await inject_service_id_if_missing(
                http_client=http_client,
                task_type=payload.task_type,
                body_dict=body_dict,
                user_id=user_id,
                tenant_id=tenant_id,
                latency_policy=latency_policy_header,
                cost_policy=cost_policy_header,
                accuracy_policy=accuracy_policy_header,
                is_context_aware=is_context_aware,
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
            # Only include if at least one policy value is present
            if not any(service_policy_dict.values()):
                service_policy_dict = None
    
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
        tenant_id=actual_tenant_id,  # null for free users, actual tenant_id for tenant users
        is_free_user=is_free_user,
        tenant_policy=tenant_policy_dict,
        service_policy=service_policy_dict,
        scoring_details=scoring_details,
        context_aware_result=context_aware_result,
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

