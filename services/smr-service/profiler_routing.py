import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from db_operations import get_model_details

try:
    from ai4icore_logging import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover - fallback logging
    import logging

    logger = logging.getLogger(__name__)


REQUEST_PROFILER_SERVICE_URL = os.getenv(
    "REQUEST_PROFILER_SERVICE_URL", "http://request-profiler-service:8000"
)


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


def compute_profiler_match_score(
    service: Dict[str, Any],
    profiler_domain: Optional[str],
    profiler_complexity: Optional[str],
    model_domains: Optional[List[str]],
) -> float:
    """
    Compute a match score for a service based on profiler results.
    Domain matching is PRIMARY - services with matching domain get high base score.
    Complexity is used as TIEBREAKER only when domain matches are equal.

    Scoring strategy:
    - Domain exact match: 10000 points
    - Domain partial match: 5000 points
    - Domain mismatch: 0 points
    - Complexity exact match: +100 points (tiebreaker)
    - Complexity partial match: +50 points (tiebreaker)
    - Complexity mismatch: +0 points

    This ensures domain always takes precedence over complexity.

    Args:
        service: Service dictionary from model management
        profiler_domain: Domain label from profiler (e.g., "medical")
        profiler_complexity: Complexity level from profiler (e.g., "LOW", "MEDIUM", "HIGH")
        model_domains: List of domains supported by the model (from model metadata or service policy)

    Returns:
        Match score (higher is better, typically 0-10100 range)
    """
    score = 0.0

    # Get domain from service policy first, then fall back to model_domains
    service_policy = service.get("policy") or {}
    service_domain = None
    if isinstance(service_policy, dict):
        service_domain = service_policy.get("domain")
        if isinstance(service_domain, str):
            # Convert string to list for consistent processing
            domains_to_check = [service_domain]
        elif isinstance(service_domain, list):
            domains_to_check = service_domain
        else:
            domains_to_check = None
    else:
        domains_to_check = None

    # Fall back to model_domains if not in service policy
    if not domains_to_check and model_domains:
        domains_to_check = model_domains

    # Domain matching (PRIMARY - high base score)
    domain_match_score = 0.0
    if profiler_domain and domains_to_check:
        # Check if profiler domain matches any service/model domain (case-insensitive)
        profiler_domain_lower = profiler_domain.lower()
        domains_lower = [d.lower() for d in domains_to_check if isinstance(d, str)]
        if profiler_domain_lower in domains_lower:
            # Exact domain match - highest priority
            domain_match_score = 10000.0
        else:
            # Partial match (e.g., "medical" matches "medical-legal")
            for domain in domains_lower:
                if profiler_domain_lower in domain or domain in profiler_domain_lower:
                    domain_match_score = 5000.0  # Partial match gets half points
                    break
            # If no match found, domain_match_score stays 0 (mismatch)
    # If domains_to_check is None or profiler_domain is None, domain_match_score stays 0

    score = domain_match_score

    # Complexity matching (TIEBREAKER - only adds small bonus, never overrides domain)
    # Only add complexity bonus if domain matched (to break ties among domain-matched services)
    complexity_bonus = 0.0
    if domain_match_score > 0 and profiler_complexity:
        # Get complexity from service policy first
        service_complexity = None
        if isinstance(service_policy, dict):
            service_complexity = service_policy.get("complexity")

        if service_complexity:
            # Direct match from policy
            if str(service_complexity).lower() == profiler_complexity.lower():
                complexity_bonus = 100.0
            else:
                # Partial match - check if they're similar
                complexity_map = {
                    "low": ["low", "simple", "easy"],
                    "medium": ["medium", "moderate"],
                    "high": ["high", "complex", "difficult"]
                }
                profiler_comp_lower = profiler_complexity.lower()
                service_comp_lower = str(service_complexity).lower()
                if profiler_comp_lower in complexity_map.get(service_comp_lower, []):
                    complexity_bonus = 50.0
        else:
            # Fall back to service description check
            service_desc = str(service.get("serviceDescription", "")).lower()
            if profiler_complexity.lower() in service_desc:
                complexity_bonus = 100.0
            # If no match, give partial credit for any complexity mention
            elif any(level in service_desc for level in ["low", "medium", "high", "simple", "complex"]):
                complexity_bonus = 50.0

    # Add complexity bonus to score (only if domain matched)
    score += complexity_bonus

    return score


async def select_service_by_profiler(
    http_client: httpx.AsyncClient,
    services: List[Dict[str, Any]],
    profiler_domain: Optional[str],
    profiler_complexity: Optional[str],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Select the best service based on profiler domain and complexity matching.

    Args:
        http_client: HTTP client for making requests
        services: List of candidate services
        profiler_domain: Domain label from profiler
        profiler_complexity: Complexity level from profiler

    Returns:
        Tuple of (selected_service, fallback_service, scoring_details)
        fallback_service is None if there's only one service or no suitable fallback.
    """
    if not services:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_SERVICES_AVAILABLE",
                "message": "No candidate services available for routing.",
            },
        )

    # Filter out unhealthy/unpublished services
    healthy_services = []
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

        healthy_services.append(svc)

    if not healthy_services:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "NO_HEALTHY_SERVICES",
                "message": "No healthy services available for routing.",
            },
        )

    # Compute match scores for each service
    # First try to get domain from service policy, then fall back to fetching from model
    scored_services = []
    for svc in healthy_services:
        model_id = svc.get("modelId")
        model_domains = None

        # Try to fetch model domain only if not in service policy
        service_policy = svc.get("policy") or {}
        if isinstance(service_policy, dict) and service_policy.get("domain"):
            # Domain is in service policy, no need to fetch
            logger.debug(
                "SMR: Using domain from service policy",
                extra={
                    "context": {
                        "service_id": svc.get("serviceId"),
                        "domain": service_policy.get("domain"),
                    }
                }
            )
        elif model_id:
            # Fetch model domain as fallback
            model_domains = await fetch_model_domain(http_client, model_id)

        # Compute match score
        match_score = compute_profiler_match_score(
            service=svc,
            profiler_domain=profiler_domain,
            profiler_complexity=profiler_complexity,
            model_domains=model_domains,
        )

        scored_services.append((match_score, svc, model_domains))

        # Get service policy for logging
        svc_policy = svc.get("policy") or {}
        logger.info(
            "SMR: Profiler match score computed",
            extra={
                "context": {
                    "service_id": svc.get("serviceId"),
                    "match_score": match_score,
                    "profiler_domain": profiler_domain,
                    "profiler_complexity": profiler_complexity,
                    "service_domain": svc_policy.get("domain") if isinstance(svc_policy, dict) else None,
                    "service_complexity": svc_policy.get("complexity") if isinstance(svc_policy, dict) else None,
                    "model_domains": model_domains,
                    "full_service_policy": svc_policy if isinstance(svc_policy, dict) else None,
                }
            }
        )

    # Helper function to extract domain and complexity scores separately for tie-breaking
    def get_domain_complexity_scores(service_tuple):
        """Extract domain and complexity scores from service for tie-breaking."""
        match_score, svc, _ = service_tuple
        service_policy = svc.get("policy") or {}

        # Extract domain match score (base score without complexity bonus)
        domain_score = 0.0
        if profiler_domain:
            service_domain = None
            if isinstance(service_policy, dict):
                service_domain = service_policy.get("domain")
                if isinstance(service_domain, str):
                    domains_to_check = [service_domain]
                elif isinstance(service_domain, list):
                    domains_to_check = service_domain
                else:
                    domains_to_check = None
            else:
                domains_to_check = None

            # Also check model_domains if available
            model_domains_inner = service_tuple[2] if len(service_tuple) > 2 else None
            if not domains_to_check and model_domains_inner:
                domains_to_check = model_domains_inner

            if domains_to_check:
                profiler_domain_lower = profiler_domain.lower()
                domains_lower = [d.lower() for d in domains_to_check if isinstance(d, str)]
                if profiler_domain_lower in domains_lower:
                    domain_score = 10000.0
                else:
                    for domain in domains_lower:
                        if profiler_domain_lower in domain or domain in profiler_domain_lower:
                            domain_score = 5000.0
                            break

        # Complexity bonus is the difference between total score and domain score
        complexity_score = match_score - domain_score

        return domain_score, complexity_score

    # Sort by match score (descending), then by complexity (descending), then by service_id (ascending) for tie-breaking
    # This ensures proper tie-breaking: domain -> complexity -> lexicographic
    scored_services.sort(key=lambda x: (
        -x[0],  # Total match score (descending)
        -get_domain_complexity_scores(x)[1],  # Complexity score (descending) - for tie-breaking when domain matches
        x[1].get("serviceId", "")  # Lexicographic order (ascending) - final tie-breaker
    ))

    selected_service = scored_services[0][1]
    top_score = scored_services[0][0]

    # Check for ties at total match score level
    tied_services = [x for x in scored_services if x[0] == top_score]

    # Log all scores for debugging
    all_scores = []
    for x in scored_services:
        domain_score, complexity_score = get_domain_complexity_scores(x)
        all_scores.append({
            "service_id": x[1].get("serviceId"),
            "total_score": x[0],
            "domain_score": domain_score,
            "complexity_score": complexity_score,
        })
    logger.info(
        "SMR: All profiler match scores",
        extra={
            "context": {
                "profiler_domain": profiler_domain,
                "profiler_complexity": profiler_complexity,
                "all_scores": all_scores,
            }
        }
    )

    scoring_details: Dict[str, Any] = {
        "tie_level": 0,
        "tie_breaker_level": {
            "first": None,
            "second": None,
        },
        "profiler_domain": profiler_domain,
        "profiler_complexity": profiler_complexity,
    }

    if len(tied_services) > 1:
        # Check if tied services have same domain match
        top_domain_score, top_complexity_score = get_domain_complexity_scores(tied_services[0])
        domain_tied = [x for x in tied_services if get_domain_complexity_scores(x)[0] == top_domain_score]

        logger.info(
            "SMR: Checking tie-breaking for profiler selection",
            extra={
                "context": {
                    "tied_count": len(tied_services),
                    "top_total_score": top_score,
                    "top_domain_score": top_domain_score,
                    "top_complexity_score": top_complexity_score,
                    "domain_tied_count": len(domain_tied),
                    "tied_service_ids": [x[1].get("serviceId") for x in tied_services],
                }
            }
        )

        if len(domain_tied) > 1:
            # Domain matches - check complexity as first tie-breaker
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "complexity_match"

            # Check if complexity also ties
            complexity_tied = [x for x in domain_tied if get_domain_complexity_scores(x)[1] == top_complexity_score]
            if len(complexity_tied) > 1:
                # Complexity also ties - use lexicographic order as second tie-breaker
                scoring_details["tie_level"] = 2
                scoring_details["tie_breaker_level"]["second"] = "lexicographic_order"
                logger.info(
                    "SMR: Tie broken by complexity then lexicographic order",
                    extra={
                        "context": {
                            "complexity_tied_count": len(complexity_tied),
                            "tie_breaker_first": "complexity_match",
                            "tie_breaker_second": "lexicographic_order",
                        }
                    }
                )
            else:
                # Tie broken by complexity
                scoring_details["tie_breaker_level"]["second"] = None
                logger.info(
                    "SMR: Tie broken by complexity match",
                    extra={
                        "context": {
                            "tie_breaker_first": "complexity_match",
                            "tie_breaker_second": None,
                        }
                    }
                )
        else:
            # This shouldn't happen if sorting is correct, but handle it
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lexicographic_order"
            scoring_details["tie_breaker_level"]["second"] = None
            logger.warning(
                "SMR: Unexpected tie scenario - services tied but different domain scores",
                extra={
                    "context": {
                        "tied_count": len(tied_services),
                        "domain_tied_count": len(domain_tied),
                    }
                }
            )

    # Get fallback service (second best) if available
    fallback_service = None
    if len(scored_services) > 1:
        fallback_service = scored_services[1][1]

    logger.info(
        "SMR: Service selected by profiler",
        extra={
            "context": {
                "selected_service_id": selected_service.get("serviceId"),
                "fallback_service_id": fallback_service.get("serviceId") if fallback_service else None,
                "match_score": top_score,
                "profiler_domain": profiler_domain,
                "profiler_complexity": profiler_complexity,
                "tied_count": len(tied_services),
            }
        }
    )

    return selected_service, fallback_service, scoring_details

