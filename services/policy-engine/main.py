import time
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app
from app.models import PolicyRequest, PolicyResponse, LatencyPolicy, CostPolicy, AccuracyPolicy
from app.engine import evaluate_rules, FALLBACK_FLAGS
from app.repository import get_tenant_policy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy-engine")

# Metrics
POLICY_REQUESTS = Counter('smr_policy_requests_total', 'Total evaluations')
POLICY_LATENCY = Histogram('smr_policy_latency_seconds', 'Evaluation time')
POLICY_ERRORS = Counter('smr_policy_errors_total', 'Total errors')

app = FastAPI(title="AI4I Policy Engine", version="1.7.0")

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
CURRENT_POLICY_VERSION = "v1.0"

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": CURRENT_POLICY_VERSION}

@app.post("/v1/policy/evaluate", response_model=PolicyResponse, response_model_exclude_none=False)
async def evaluate_policy(request: PolicyRequest):
    start_time = time.time()
    POLICY_REQUESTS.inc()
    
    try:
        # 1. Identify User & Defaults
        lat = LatencyPolicy.MEDIUM
        cost = CostPolicy.TIER_2
        acc = AccuracyPolicy.STANDARD
        is_free_user = True

        # 2. DB Lookup
        if request.tenant_id:
            is_free_user = False
            db_policy = await get_tenant_policy(request.tenant_id)
            if db_policy:
                # Tenant-specific policy found in DB
                lat = db_policy["latency"]
                cost = db_policy["cost"]
                acc = db_policy["accuracy"]
            else:
                # No tenant-specific row → force "everything low" by default
                # Latency: LOW, Cost: TIER_1 (cheapest), Accuracy: STANDARD
                lat = LatencyPolicy.LOW
                cost = CostPolicy.TIER_1
                acc = AccuracyPolicy.STANDARD
            
            # Allow explicit overrides from request (highest priority)
            if request.latency_policy:
                lat = request.latency_policy
            if request.cost_policy:
                cost = request.cost_policy
            if request.accuracy_policy:
                acc = request.accuracy_policy
        else:
            # No tenant_id, but check if explicit policies are provided
            # If explicit policies are provided, use them
            if request.latency_policy: lat = request.latency_policy
            if request.cost_policy: cost = request.cost_policy
            if request.accuracy_policy: acc = request.accuracy_policy
            
            # Check if this matches Free tier pattern (high/tier_1/sensitive)
            # If so, keep is_free_user = True to return distilled
            # Otherwise, treat as non-free user
            if (lat == LatencyPolicy.HIGH and cost == CostPolicy.TIER_1 and acc == AccuracyPolicy.SENSITIVE):
                is_free_user = True
            else:
                is_free_user = False

        # 3. Evaluate Logic
        pid, flags = evaluate_rules(is_free_user, lat, cost, acc)

        POLICY_LATENCY.observe(time.time() - start_time)
        
        # Convert enum values to strings for JSON serialization
        latency_val = lat.value if lat else None
        cost_val = cost.value if cost else None
        accuracy_val = acc.value if acc else None
        
        logger.info(f"Policy evaluation: tenant_id={request.tenant_id}, latency={latency_val}, cost={cost_val}, accuracy={accuracy_val}, policy_id={pid}")
        
        response = PolicyResponse(
            policy_id=pid,
            policy_version=CURRENT_POLICY_VERSION, # <--- RETURNING VERSION
            routing_flags=flags,
            latency_policy=latency_val,
            cost_policy=cost_val,
            accuracy_policy=accuracy_val
        )
        
        # Log the response to verify values are set
        logger.info(f"PolicyResponse: {response.model_dump(exclude_none=False)}")
        
        return response

    except Exception as e:
        logger.error(f"Policy Engine Critical Failure: {e}")
        POLICY_ERRORS.inc()
        return PolicyResponse(
            policy_id="fallback_sys_error",
            policy_version=CURRENT_POLICY_VERSION,
            routing_flags=FALLBACK_FLAGS,
            fallback_applied=True,
            latency_policy=LatencyPolicy.MEDIUM.value,
            cost_policy=CostPolicy.TIER_2.value,
            accuracy_policy=AccuracyPolicy.STANDARD.value
        )
