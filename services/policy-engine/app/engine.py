from app.models import RoutingFlags, LatencyPolicy, CostPolicy, AccuracyPolicy

# --- Fallback Safety Net ---
FALLBACK_FLAGS = RoutingFlags(
    model_family="general",
    model_variant="standard",
    priority=5,
    routing_strategy="balanced",
    max_cost_usd=0.05
)

def evaluate_rules(
    is_free_user: bool,
    latency: LatencyPolicy, 
    cost: CostPolicy, 
    accuracy: AccuracyPolicy
) -> tuple[str, RoutingFlags]:
    """
    Implements the 3-Dimension Matrix from 'AI4I Policies.docx'
    """
    
    # 1. Force "Free Tier" Overrides (Hard Rule)
    if is_free_user:
        return "pol_hard_free_tier", RoutingFlags(
            model_family="distilled",
            model_variant="student", # Always cheapest
            priority=1,
            routing_strategy="strict_cost_limit",
            max_cost_usd=0.00 # Zero cost
        )

    # 2. Enterprise Tier: tier_3 + standard accuracy -> state_of_art
    if cost == CostPolicy.TIER_3 and accuracy == AccuracyPolicy.STANDARD:
        return "pol_enterprise_tier", RoutingFlags(
            model_family="state_of_art",
            model_variant="teacher",
            priority=9,
            routing_strategy="quality_first",
            max_cost_usd=0.10
        )

    # 3. Paid Tier: tier_2 + sensitive accuracy -> balanced
    if cost == CostPolicy.TIER_2 and accuracy == AccuracyPolicy.SENSITIVE:
        return "pol_paid_tier", RoutingFlags(
            model_family="balanced",
            model_variant="standard",
            priority=5,
            routing_strategy="balanced",
            max_cost_usd=0.05
        )

    # 4. Accuracy Check (Highest Precedence for other cases)
    # If user needs "Sensitive" accuracy, we try to give Teacher models
    # UNLESS Cost is Tier 1 (Strict Limits)
    if accuracy == AccuracyPolicy.SENSITIVE:
        if cost == CostPolicy.TIER_1:
            # Conflict: Wants High Quality but has Low Budget -> Give Standard
            return "pol_conflict_quality_budget", RoutingFlags(
                model_family="balanced",
                model_variant="standard",
                priority=5,
                routing_strategy="balanced_fallback",
                max_cost_usd=0.02
            )
        else:
            # Grant High Quality
            return "pol_high_accuracy", RoutingFlags(
                model_family="state_of_the_art",
                model_variant="teacher", # e.g., GPT-4 / Whisper Large
                priority=8,
                routing_strategy="quality_first",
                max_cost_usd=0.10
            )

    # 5. Latency Check
    if latency == LatencyPolicy.LOW:
        # Wants Speed (Turbo)
        return "pol_low_latency", RoutingFlags(
            model_family="optimized",
            model_variant="turbo", # e.g. Whisper Turbo
            priority=10,
            routing_strategy="lowest_latency",
            max_cost_usd=0.05
        )

    # 6. Default / Balanced
    return "pol_standard_balanced", FALLBACK_FLAGS
