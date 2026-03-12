"""
SMR Scoring Logic

This module contains all service scoring, ranking, and selection functions
used by the Smart Model Router (SMR) service.

Functions:
- _compute_latency_score_for_service: Latency-based score from benchmarks
- _get_cost_tier_value: Extract numeric cost tier for sorting
- _compute_policy_match_score_for_service: Policy match score (latency/cost/accuracy)
- validate_policy_combinations: Validate that policy combos are legal
- select_service_deterministically: Select best service by policy/latency/cost scoring
- compute_profiler_match_score: Domain+complexity score from profiler output
- select_service_by_profiler: Select best service using profiler domain/complexity
"""

from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

try:
    from ai4icore_logging import get_logger

    logger = get_logger(__name__)
except Exception:  # pragma: no cover - fallback logging
    import logging

    logger = logging.getLogger(__name__)


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
                    },
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
                    },
                },
            )


def select_service_deterministically(
    services: List[Dict[str, Any]],
    preferred_language: Optional[str],
    latency_policy: Optional[str] = None,
    cost_policy: Optional[str] = None,
    accuracy_policy: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Deterministically select the best service from candidates.
    Returns (selected_service, fallback_service, scoring_details).
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
                },
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
        },
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
                "all_scores": [
                    {
                        "service_id": x[1],
                        "score": x[0],
                        "cost_tier": _get_cost_tier_value(x[2].get("policy")),
                    }
                    for x in policy_scored[:10]  # First 10
                ],
            },
        )

        if len(tied_services) > 1:
            # There is a tie at policy score level
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"

            # Check if tie was broken by cost tier
            top_cost_tier = _get_cost_tier_value(tied_services[0][2].get("policy"))
            cost_tied = [
                x for x in tied_services if _get_cost_tier_value(x[2].get("policy")) == top_cost_tier
            ]

            logger.info(
                "SMR: Tie detected, checking cost tier break",
                extra={
                    "tied_count": len(tied_services),
                    "top_cost_tier": top_cost_tier,
                    "cost_tied_count": len(cost_tied),
                    "tied_service_ids": [x[1] for x in tied_services],
                },
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
            scoring_details["tie_breaker_level"]["first"] = None
            scoring_details["tie_breaker_level"]["second"] = None

        # Get fallback service (second best) if available
        fallback_service = None
        if len(policy_scored) > 1:
            fallback_service = policy_scored[1][2]

        return selected, fallback_service, scoring_details

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
            },
        )

        if len(tied_services) > 1:
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
            top_cost_tier = _get_cost_tier_value(tied_services[0][2].get("policy"))
            cost_tied = [
                x for x in tied_services if _get_cost_tier_value(x[2].get("policy")) == top_cost_tier
            ]
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

        # Get fallback service (second best) if available
        fallback_service = None
        if len(scored) > 1:
            fallback_service = scored[1][2]

        return selected, fallback_service, scoring_details

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
        cost_tied = [
            x for x in fallback if _get_cost_tier_value(x[1].get("policy")) == top_cost_tier
        ]
        if len(cost_tied) > 1:
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "lowest_cost"
            scoring_details["tie_breaker_level"]["second"] = "lexicographic_order"
        else:
            # No tie - don't populate tie_breaker_level
            scoring_details["tie_breaker_level"]["first"] = None
            scoring_details["tie_breaker_level"]["second"] = None

        # Get fallback service (second best) if available
        fallback_service = None
        if len(fallback) > 1:
            fallback_service = fallback[1][1]

        return selected, fallback_service, scoring_details

    raise HTTPException(
        status_code=503,
        detail={
            "code": "NO_HEALTHY_SERVICES",
            "message": "No healthy services available for routing.",
        },
    )


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
                    "high": ["high", "complex", "difficult"],
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
            elif any(
                level in service_desc for level in ["low", "medium", "high", "simple", "complex"]
            ):
                complexity_bonus = 50.0

    # Add complexity bonus to score (only if domain matched)
    score += complexity_bonus

    return score


async def select_service_by_profiler(
    http_client: Any,
    services: List[Dict[str, Any]],
    profiler_domain: Optional[str],
    profiler_complexity: Optional[str],
    fetch_model_domain_fn: Any,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Select the best service based on profiler domain and complexity matching.

    Args:
        http_client: HTTP client for making requests
        services: List of candidate services
        profiler_domain: Domain label from profiler
        profiler_complexity: Complexity level from profiler
        fetch_model_domain_fn: Async callable to fetch model domain by model_id

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
                },
            )
        elif model_id:
            # Fetch model domain as fallback
            model_domains = await fetch_model_domain_fn(http_client, model_id)

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
            },
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
            mdl_domains = service_tuple[2] if len(service_tuple) > 2 else None
            if not domains_to_check and mdl_domains:
                domains_to_check = mdl_domains

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

    # Sort by match score (descending), then by complexity (descending), then by service_id (ascending)
    # This ensures proper tie-breaking: domain -> complexity -> lexicographic
    scored_services.sort(
        key=lambda x: (
            -x[0],  # Total match score (descending)
            -get_domain_complexity_scores(x)[1],  # Complexity score (descending)
            x[1].get("serviceId", ""),  # Lexicographic order (ascending)
        )
    )

    selected_service = scored_services[0][1]
    top_score = scored_services[0][0]

    # Check for ties at total match score level
    tied_services = [x for x in scored_services if x[0] == top_score]

    # Log all scores for debugging
    all_scores = []
    for x in scored_services:
        domain_score, complexity_score = get_domain_complexity_scores(x)
        all_scores.append(
            {
                "service_id": x[1].get("serviceId"),
                "total_score": x[0],
                "domain_score": domain_score,
                "complexity_score": complexity_score,
            }
        )
    logger.info(
        "SMR: All profiler match scores",
        extra={
            "context": {
                "profiler_domain": profiler_domain,
                "profiler_complexity": profiler_complexity,
                "all_scores": all_scores,
            }
        },
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
        domain_tied = [
            x for x in tied_services if get_domain_complexity_scores(x)[0] == top_domain_score
        ]

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
            },
        )

        if len(domain_tied) > 1:
            # Domain matches - check complexity as first tie-breaker
            scoring_details["tie_level"] = 1
            scoring_details["tie_breaker_level"]["first"] = "complexity_match"

            # Check if complexity also ties
            complexity_tied = [
                x
                for x in domain_tied
                if get_domain_complexity_scores(x)[1] == top_complexity_score
            ]
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
                    },
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
                    },
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
                },
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
        },
    )

    return selected_service, fallback_service, scoring_details
