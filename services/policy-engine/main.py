import time
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.models import (
    PolicyRequest,
    PolicyResponse,
    LatencyPolicy,
    CostPolicy,
    AccuracyPolicy,
)
from app.repository import get_tenant_policy
from app.database import init_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy-engine")

# Metrics
POLICY_REQUESTS = Counter("smr_policy_requests_total", "Total evaluations")
POLICY_LATENCY = Histogram("smr_policy_latency_seconds", "Evaluation time")
POLICY_ERRORS = Counter("smr_policy_errors_total", "Total errors")

app = FastAPI(title="AI4I Policy Engine", version="2.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/metrics", make_asgi_app())

# Define current version constant
CURRENT_POLICY_VERSION = "v2.0"


@app.on_event("startup")
async def startup_event():
    """
    Initialize database tables on service startup.
    Creates the table if it doesn't exist, skips if it already exists.
    """
    logger.info("Starting policy-engine service...")
    try:
        await init_database()
        logger.info("Policy-engine service started successfully")
    except Exception as e:
        logger.error(f"Failed to start policy-engine service: {e}")
        raise


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": CURRENT_POLICY_VERSION}


@app.post(
    "/v1/policy/evaluate",
    response_model=PolicyResponse,
    response_model_exclude_none=False,
)
async def evaluate_policy(request: PolicyRequest):
    """
    Simplified Policy Engine:
    - Reads tenant-specific latency/cost/accuracy from DB (if present)
    - Applies explicit overrides from the request (highest priority)
    - Returns only latency/cost/accuracy plus a simple policy_id/version for observability

    All "routing_flags" and model-family selection logic have been removed.
    SMR will use only these three dimensions for routing decisions.
    """
    start_time = time.time()
    POLICY_REQUESTS.inc()

    try:
        # 1. Start with global defaults
        lat = LatencyPolicy.MEDIUM
        cost = CostPolicy.TIER_2
        acc = AccuracyPolicy.STANDARD
        policy_id = "default_policy"
        fallback_applied = False

        # 2. Tenant-specific policy lookup
        if request.tenant_id:
            db_policy = await get_tenant_policy(request.tenant_id)
            if db_policy:
                lat = db_policy["latency"]
                cost = db_policy["cost"]
                acc = db_policy["accuracy"]
                policy_id = "tenant_db_policy"
            else:
                # No tenant-specific row → deterministic tenant default
                lat = LatencyPolicy.LOW
                cost = CostPolicy.TIER_1
                acc = AccuracyPolicy.STANDARD
                policy_id = "tenant_default_policy"

        # 3. Apply explicit overrides from request (highest priority)
        if request.latency_policy:
            lat = request.latency_policy
            policy_id = "explicit_override_policy"
        if request.cost_policy:
            cost = request.cost_policy
            policy_id = "explicit_override_policy"
        if request.accuracy_policy:
            acc = request.accuracy_policy
            policy_id = "explicit_override_policy"

        POLICY_LATENCY.observe(time.time() - start_time)

        # Convert enum values to strings for JSON serialization
        latency_val = lat.value if lat else None
        cost_val = cost.value if cost else None
        accuracy_val = acc.value if acc else None

        logger.info(
            "Policy evaluation: tenant_id=%s, latency=%s, cost=%s, accuracy=%s, policy_id=%s",
            request.tenant_id,
            latency_val,
            cost_val,
            accuracy_val,
            policy_id,
        )

        response = PolicyResponse(
            policy_id=policy_id,
            policy_version=CURRENT_POLICY_VERSION,
            fallback_applied=fallback_applied,
            latency_policy=latency_val,
            cost_policy=cost_val,
            accuracy_policy=accuracy_val,
        )

        logger.info(
            "PolicyResponse: %s",
            response.model_dump(exclude_none=False),
        )

        return response

    except Exception as e:
        logger.error(f"Policy Engine Critical Failure: {e}")
        POLICY_ERRORS.inc()
        return PolicyResponse(
            policy_id="fallback_sys_error",
            policy_version=CURRENT_POLICY_VERSION,
            fallback_applied=True,
            latency_policy=LatencyPolicy.MEDIUM.value,
            cost_policy=CostPolicy.TIER_2.value,
            accuracy_policy=AccuracyPolicy.STANDARD.value,
        )
