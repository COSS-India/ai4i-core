"""
Smart Model Router core logic for API Gateway.

This module contains pure routing logic:
- Calls Policy Engine for latency/cost/accuracy evaluation
- Fetches candidate services from Model Management
- Deterministically selects a service based on benchmarks and health
- Maps task types to downstream service/inference paths

FastAPI endpoint definitions remain in main.py and delegate into these helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import os

import httpx
from fastapi import HTTPException

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


async def call_policy_engine_for_smr(
    http_client: httpx.AsyncClient,
    user_id: Optional[str],
    tenant_id: Optional[str],
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str],
) -> Dict[str, Any]:
    """
    Call Policy Engine to evaluate latency/cost/accuracy policy for this request.

    The policy inputs are plain strings (e.g. "low", "tier_2", "standard") so this
    helper is independent of any specific Enum types in main.py.
    """
    payload: Dict[str, Any] = {
        "user_id": user_id or "anonymous",
        "tenant_id": tenant_id,
        "latency_policy": latency_policy,
        "cost_policy": cost_policy,
        "accuracy_policy": accuracy_policy,
    }

    # Strip out None values
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

    result = resp.json()
    logger.info(
        "SMR: Policy-engine response received",
        extra={
            "context": {
                "policy_id": result.get("policy_id"),
                "policy_version": result.get("policy_version"),
                "routing_flags": result.get("routing_flags"),
            }
        },
    )
    return result


async def fetch_candidate_services_for_task(
    http_client: httpx.AsyncClient,
    task_type: str,
) -> List[Dict[str, Any]]:
    """
    Fetch candidate services for a given task type from model-management-service.

    Returns a list of raw dicts (service entries). We intentionally do not
    depend on the ServiceListResponse Pydantic model to avoid circular imports.
    """
    params = {
        "task_type": task_type,
        "is_published": "true",
    }

    logger.info(
        "SMR: Fetching candidate services from model-management",
        extra={"context": {"task_type": task_type}},
    )
    try:
        resp = await http_client.get(
            f"{MODEL_MANAGEMENT_SERVICE_URL}/services/details/list_services",
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
        logger.warning(
            "Model Management returned non-200 status",
            extra={"status_code": resp.status_code, "body": resp.text},
        )
        raise HTTPException(
            status_code=resp.status_code,
            detail={
                "code": "MODEL_MANAGEMENT_ERROR",
                "message": "Failed to fetch candidate services for routing.",
            },
        )

    data = resp.json()
    logger.info(
        "SMR: Model-management candidate services response",
        extra={
            "context": {
                "task_type": task_type,
                "service_count": len(data) if isinstance(data, list) else "n/a",
            }
        },
    )
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


def _compute_latency_score_for_service(
    svc: Dict[str, Any],
    preferred_language: Optional[str],
) -> Optional[int]:
    """
    Compute a latency score for a service based on its benchmarks.

    Benchmarks schema is expected to be:
      {
        "<key>": [
          {
            "output_length": ...,
            "generated": ...,
            "actual": ...,
            "throughput": ...,
            "50%": <p50>,
            "99%": <p99>,
            "language": "<lang>"
          },
          ...
        ],
        ...
      }
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

    return min(latencies) if latencies else None


def _compute_policy_match_score_for_service(
    svc: Dict[str, Any],
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str],
) -> Optional[int]:
    """
    Compute how well a service matches the requested latency/cost/accuracy policy.

    Priority:
    1. Use service's explicit policy data from `policy` column (if available)
    2. Fall back to parsing serviceDescription (for backward compatibility)

    Lower score = better match. None = no usable signal.
    """
    if not (latency_policy or cost_policy or accuracy_policy):
        return None

    score = 0
    
    # First, try to use explicit policy data from service's policy column
    service_policy = svc.get("policy")
    if service_policy and isinstance(service_policy, dict):
        # Service has explicit policy data - use it for exact matching
        service_latency = str(service_policy.get("latency", "")).lower() if service_policy.get("latency") else None
        service_cost = str(service_policy.get("cost", "")).lower() if service_policy.get("cost") else None
        service_accuracy = str(service_policy.get("accuracy", "")).lower() if service_policy.get("accuracy") else None
        
        # Latency: exact match
        if latency_policy:
            lp = str(latency_policy).lower()
            if service_latency and service_latency != lp:
                score += 1
            elif not service_latency:
                # Service doesn't have latency policy, can't match
                score += 1
        
        # Cost: exact match
        if cost_policy:
            cp = str(cost_policy).lower()
            if service_cost and service_cost != cp:
                score += 1
            elif not service_cost:
                # Service doesn't have cost policy, can't match
                score += 1
        
        # Accuracy: exact match
        if accuracy_policy:
            ap = str(accuracy_policy).lower()
            if service_accuracy and service_accuracy != ap:
                score += 1
            elif not service_accuracy:
                # Service doesn't have accuracy policy, can't match
                score += 1
        
        # If we have policy data, return the score (even if 0 = perfect match)
        return score
    
    # Fallback: parse from serviceDescription (backward compatibility)
    desc = str(svc.get("serviceDescription") or "").lower()
    if not desc:
        return None

    # Latency: LOW / MEDIUM / HIGH
    if latency_policy:
        lp = str(latency_policy).lower()
        if lp == "low":
            if "low latency" not in desc:
                score += 1
        elif lp == "medium":
            if "medium latency" not in desc:
                score += 1
        elif lp == "high":
            if "high latency" not in desc:
                score += 1

    # Cost: tier_1 / tier_2 / tier_3
    if cost_policy:
        cp = str(cost_policy).lower()
        if cp.startswith("tier_1") and "tier_1 cost" not in desc:
            score += 1
        elif cp.startswith("tier_2") and "tier_2 cost" not in desc:
            score += 1
        elif cp.startswith("tier_3") and "tier_3 cost" not in desc:
            score += 1

    # Accuracy: sensitive / standard
    if accuracy_policy:
        ap = str(accuracy_policy).lower()
        if ap == "sensitive":
            if "sensitive accuracy" not in desc:
                score += 1
        elif ap == "standard":
            if "standard accuracy" not in desc:
                score += 1

    # If we didn't penalize anything, it's a strong match (score 0).
    # If everything mismatched, score will be > 0 but still usable for ranking.
    return score


def select_service_deterministically(
    services: List[Dict[str, Any]],
    preferred_language: Optional[str],
    latency_policy: Optional[str] = None,
    cost_policy: Optional[str] = None,
    accuracy_policy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically select the best service from candidates using benchmark latency.

    - Prefer services with known latency scores (p50 from benchmarks).
    - Among those, choose the one with lowest latency.
    - Tie-breaker: lexicographically smallest serviceId to ensure determinism.
    - If no benchmarks are available, fall back to lexicographically smallest healthy serviceId.
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
        # Check publish flag
        if svc.get("isPublished") is False:
            continue

        # Health check (if information is present)
        health = svc.get("healthStatus") or {}
        if isinstance(health, dict):
            status = str(health.get("status", "")).lower()
            if status and status not in ("healthy", "up"):
                continue

        service_id = str(svc.get("serviceId", ""))
        if not service_id:
            continue

        # 1) Try to use explicit latency/cost/accuracy policy match first
        policy_score = _compute_policy_match_score_for_service(
            svc,
            latency_policy=latency_policy,
            cost_policy=cost_policy,
            accuracy_policy=accuracy_policy,
        )
        if policy_score is not None:
            policy_scored.append((policy_score, service_id, svc))
            continue

        # 2) Fallback: use benchmark-based latency score
        latency_score = _compute_latency_score_for_service(svc, preferred_language)
        if latency_score is not None:
            scored.append((latency_score, service_id, svc))
        else:
            fallback.append((service_id, svc))

    # Prefer services that match the tenant's latency/cost/accuracy policy
    if policy_scored:
        # Lower policy_score is better; tie-breaker on service_id
        policy_scored.sort(key=lambda x: (x[0], x[1]))
        return policy_scored[0][2]

    if scored:
        scored.sort(key=lambda x: (x[0], x[1]))
        return scored[0][2]

    if fallback:
        fallback.sort(key=lambda x: x[0])
        return fallback[0][1]

    raise HTTPException(
        status_code=503,
        detail={
            "code": "NO_HEALTHY_SERVICES",
            "message": "No healthy services available for routing.",
        },
    )


def get_downstream_for_task(task_type: str) -> Tuple[str, str]:
    """
    Map task_type string to (service_name, inference_path) for downstream call.

    This keeps Smart Model Router generic while reusing existing inference endpoints.
    """
    mapping: Dict[str, Tuple[str, str]] = {
        "asr": ("asr-service", "/api/v1/asr/inference"),
        "nmt": ("nmt-service", "/api/v1/nmt/inference"),
        "tts": ("tts-service", "/api/v1/tts/inference"),
        "ocr": ("ocr-service", "/api/v1/ocr/inference"),
        "llm": ("llm-service", "/api/v1/llm/inference"),
        "transliteration": (
            "transliteration-service",
            "/api/v1/transliteration/inference",
        ),
        "language-detection": (
            "language-detection-service",
            "/api/v1/language-detection/inference",
        ),
        "speaker-diarization": (
            "speaker-diarization-service",
            "/api/v1/speaker-diarization/inference",
        ),
        "language-diarization": (
            "language-diarization-service",
            "/api/v1/language-diarization/inference",
        ),
        "audio-lang-detection": (
            "audio-lang-detection-service",
            "/api/v1/audio-lang-detection/inference",
        ),
        "ner": ("ner-service", "/api/v1/ner/inference"),
    }

    if task_type not in mapping:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_TASK",
                "message": f"Smart routing does not support task_type '{task_type}'",
            },
        )
    return mapping[task_type]


async def inject_service_id_if_missing(
    http_client: httpx.AsyncClient,
    task_type: str,
    body_dict: Dict[str, Any],
    user_id: Optional[str],
    tenant_id: Optional[str],
    latency_policy: Optional[str] = None,
    cost_policy: Optional[str] = None,
    accuracy_policy: Optional[str] = None,
) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Ensure that body_dict.config.serviceId is populated, using SMR selection if needed.

    Returns (service_id, updated_body_dict, policy_result_or_none).
    """
    # If request already includes a serviceId, trust it and do nothing
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
        return str(existing_service_id), body_dict, None

    # 1. Determine policy values
    # Priority:
    #   a) If no tenant_id -> treat as "free user" and use fixed low-cost/low-accuracy/high-latency defaults
    #   b) Else if policy headers are provided -> use them directly (skip Policy Engine)
    #   c) Else -> call Policy Engine for tenant-specific policies
    headers_provided = (
        latency_policy is not None or cost_policy is not None or accuracy_policy is not None
    )

    policy_result: Optional[Dict[str, Any]] = None
    actual_latency_policy: Optional[str] = None
    actual_cost_policy: Optional[str] = None
    actual_accuracy_policy: Optional[str] = None

    if tenant_id is None:
        # a) No tenant_id in token -> free user path
        # Do NOT call Policy Engine and ignore any policy headers.
        # Use fixed defaults:
        #   - latency: "high"      (we allow higher latency)
        #   - cost:    "tier_1"    (lowest cost)
        #   - accuracy:"standard"  (normal accuracy, not sensitive)
        actual_latency_policy = "high"
        actual_cost_policy = "tier_1"
        actual_accuracy_policy = "standard"

        policy_result = {
            "policy_id": "pol_free_user_default",
            "policy_version": "v1.0",
            "latency_policy": actual_latency_policy,
            "cost_policy": actual_cost_policy,
            "accuracy_policy": actual_accuracy_policy,
        }

        logger.info(
            "SMR: Free-user routing (no tenant_id) using fixed low-cost/low-accuracy/high-latency defaults",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "latency_policy": actual_latency_policy,
                    "cost_policy": actual_cost_policy,
                    "accuracy_policy": actual_accuracy_policy,
                    "decision": "free_user_defaults",
                }
            },
        )

    elif headers_provided:
        # Headers are present: use them directly, skip Policy Engine call
        logger.info(
            "SMR: Using policy headers directly (skipping Policy Engine)",
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
        # Use header values directly
        actual_latency_policy = latency_policy
        actual_cost_policy = cost_policy
        actual_accuracy_policy = accuracy_policy
        
        # Convert enum values to strings if needed
        if actual_latency_policy and hasattr(actual_latency_policy, 'value'):
            actual_latency_policy = actual_latency_policy.value
        if actual_cost_policy and hasattr(actual_cost_policy, 'value'):
            actual_cost_policy = actual_cost_policy.value
        if actual_accuracy_policy and hasattr(actual_accuracy_policy, 'value'):
            actual_accuracy_policy = actual_accuracy_policy.value
    else:
        # No headers provided: call Policy Engine to get tenant-specific policies
        logger.info(
            "SMR: No policy headers provided, calling Policy Engine for tenant policies",
            extra={
                "context": {
                    "task_type": task_type,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "decision": "policy_engine_lookup",
                }
            },
        )
        
        policy_result = await call_policy_engine_for_smr(
            http_client=http_client,
            user_id=user_id,
            tenant_id=tenant_id,
            latency_policy=None,  # No headers, let Policy Engine determine from tenant
            cost_policy=None,
            accuracy_policy=None,
        )

        # Extract actual policy values from policy_result (policy engine returns tenant-specific policies)
        actual_latency_policy = policy_result.get("latency_policy")
        actual_cost_policy = policy_result.get("cost_policy")
        actual_accuracy_policy = policy_result.get("accuracy_policy")
        
        # Convert enum values to strings if needed
        if actual_latency_policy and hasattr(actual_latency_policy, 'value'):
            actual_latency_policy = actual_latency_policy.value
        if actual_cost_policy and hasattr(actual_cost_policy, 'value'):
            actual_cost_policy = actual_cost_policy.value
        if actual_accuracy_policy and hasattr(actual_accuracy_policy, 'value'):
            actual_accuracy_policy = actual_accuracy_policy.value
    
    # 2. Fetch candidate services for the given task_type
    candidate_services = await fetch_candidate_services_for_task(
        http_client=http_client,
        task_type=task_type,
    )

    if not candidate_services:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_CANDIDATE_SERVICES",
                "message": "No candidate services found for the given task type.",
            },
        )

    # 3. Deterministically select best service based on tenant policy and benchmarks/health
    # Use the policy values (they may have been resolved by policy engine from tenant_id)
    selected_service = select_service_deterministically(
        candidate_services,
        preferred_language=None,
        latency_policy=actual_latency_policy,
        cost_policy=actual_cost_policy,
        accuracy_policy=actual_accuracy_policy,
    )
    service_id = str(selected_service.get("serviceId"))

    logger.info(
        "SMR: Selected service for routing",
        extra={
            "context": {
                "task_type": task_type,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "selected_service_id": service_id,
                "selected_service_name": selected_service.get("name"),
                "selected_service_benchmarks": selected_service.get("benchmarks"),
                "policy_id": policy_result.get("policy_id") if policy_result else None,
                "policy_version": policy_result.get("policy_version") if policy_result else None,
            }
        },
    )

    config["serviceId"] = service_id
    body_dict["config"] = config

    return service_id, body_dict, policy_result


