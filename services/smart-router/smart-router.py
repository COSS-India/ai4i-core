"""
Smart Router Service
Intelligent routing service for AI4I platform
"""

import logging
import os
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
import asyncio

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("smart-router")

# FastAPI app
app = FastAPI(
    title="Smart Router Service",
    version="1.0.0",
    description="Intelligent routing service for AI4I platform"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8096"))
POLICY_ENGINE_URL = os.getenv("POLICY_ENGINE_URL", "http://policy-engine:8095")
ASR_SERVICE_URL = os.getenv("ASR_SERVICE_URL", "http://asr-service:8087")
NMT_SERVICE_URL = os.getenv("NMT_SERVICE_URL", "http://nmt-service:8089")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://tts-service:8088")
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8090")
PIPELINE_SERVICE_URL = os.getenv("PIPELINE_SERVICE_URL", "http://pipeline-service:8090")

# Request/Response models
class RoutingRequest(BaseModel):
    """Request model for smart routing - accepts any service request format"""
    # Accept the original request body as-is
    input: Optional[List[Dict[str, Any]]] = Field(None, description="Input data (varies by service)")
    config: Optional[Dict[str, Any]] = Field(None, description="Service configuration")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Control configuration")
    # Additional fields that might be in the request
    audio: Optional[List[Dict[str, Any]]] = Field(None, description="Audio input (for ASR)")
    # Policy and user context (extracted from headers or request)
    user_id: Optional[str] = Field(None, description="User ID")
    tenant_id: Optional[str] = Field(None, description="Tenant ID")
    latency_policy: Optional[str] = Field(None, description="Latency policy: low, medium, high")
    cost_policy: Optional[str] = Field(None, description="Cost policy: tier_1, tier_2, tier_3")
    accuracy_policy: Optional[str] = Field(None, description="Accuracy policy: sensitive, standard")
    routing_service: Optional[str] = Field(None, description="Routing service type: Free, Paid, Enterprise (defaults to Free if invalid)")

class RoutingResponse(BaseModel):
    """Response model for smart routing"""
    routed: bool = Field(..., description="Whether request was routed")
    service_url: Optional[str] = Field(None, description="Service URL that was routed to")
    policy_id: Optional[str] = Field(None, description="Policy ID from policy engine")
    routing_flags: Optional[Dict[str, Any]] = Field(None, description="Routing flags from policy engine")
    response: Optional[Dict[str, Any]] = Field(None, description="Response from routed service")

# Service URL mapping
SERVICE_URL_MAP = {
    "asr": ASR_SERVICE_URL,
    "nmt": NMT_SERVICE_URL,
    "tts": TTS_SERVICE_URL,
    "llm": LLM_SERVICE_URL,
    "pipeline": PIPELINE_SERVICE_URL,
}

# Service endpoint mapping
SERVICE_ENDPOINT_MAP = {
    "asr": "/api/v1/asr/inference",
    "nmt": "/api/v1/nmt/inference",
    "tts": "/api/v1/tts/inference",
    "llm": "/api/v1/llm/inference",
    "pipeline": "/api/v1/pipeline/inference",
}

async def get_policy_decision(
    user_id: Optional[str],
    tenant_id: Optional[str],
    latency_policy: Optional[str],
    cost_policy: Optional[str],
    accuracy_policy: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Get routing policy decision from policy engine and print it"""
    try:
        # Use default user_id if not provided
        effective_user_id = user_id or "anonymous"
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {
                "user_id": effective_user_id,
                "tenant_id": tenant_id,
                "latency_policy": latency_policy,
                "cost_policy": cost_policy,
                "accuracy_policy": accuracy_policy,
            }
            
            print("=" * 80)
            print("🔍 CALLING POLICY ENGINE")
            print(f"   URL: {POLICY_ENGINE_URL}/v1/policy/evaluate")
            print(f"   Payload: {payload}")
            print("=" * 80)
            
            response = await client.post(
                f"{POLICY_ENGINE_URL}/v1/policy/evaluate",
                json=payload
            )
            
            if response.status_code == 200:
                policy_result = response.json()
                
                # Print policy engine response
                print("=" * 80)
                print("✅ POLICY ENGINE RESPONSE")
                print(f"   Policy ID: {policy_result.get('policy_id', 'N/A')}")
                print(f"   Policy Version: {policy_result.get('policy_version', 'N/A')}")
                print(f"   Routing Flags:")
                routing_flags = policy_result.get('routing_flags', {})
                for key, value in routing_flags.items():
                    print(f"      {key}: {value}")
                print(f"   Fallback Applied: {policy_result.get('fallback_applied', False)}")
                print("=" * 80)
                
                return policy_result
            else:
                logger.warning(f"Policy engine returned {response.status_code}: {response.text}")
                print(f"⚠️ Policy engine returned {response.status_code}: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Failed to get policy decision: {e}")
        print(f"❌ Failed to get policy decision: {e}")
        return None

async def route_to_service(
    service_type: str,
    service_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """Route request to target service"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{service_url}{endpoint}",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Service returned error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Service error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Failed to route to service: {e}")
        raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "smart-router",
        "version": "1.0.0"
    }

def detect_service_type_from_path(path: str) -> Optional[str]:
    """Detect service type from request path"""
    path_lower = path.lower()
    if '/asr' in path_lower:
        return 'asr'
    elif '/nmt' in path_lower:
        return 'nmt'
    elif '/tts' in path_lower:
        return 'tts'
    elif '/llm' in path_lower:
        return 'llm'
    elif '/pipeline' in path_lower:
        return 'pipeline'
    return None

@app.post("/api/v1/smart-router/route/{service_type:path}")
async def smart_route(service_type: str, http_request: Request):
    """
    Smart routing endpoint that:
    1. Receives request from API Gateway
    2. Evaluates policy using policy engine (prints response)
    3. Routes request to appropriate service based on policy
    4. Returns response from routed service
    
    Service types: asr, nmt, tts, llm, pipeline
    """
    try:
        # Normalize service type (remove leading/trailing slashes)
        service_type = service_type.strip('/').split('/')[0].lower()
        
        # Validate service type
        if service_type not in SERVICE_URL_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid service type: {service_type}. Must be one of: {list(SERVICE_URL_MAP.keys())}"
            )
        
        # Read request body (need to store it to recreate for downstream)
        try:
            import json
            body_bytes = await http_request.body()
            request_data = json.loads(body_bytes.decode('utf-8')) if body_bytes else {}
            
            # Recreate request body stream for downstream services
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            http_request._receive = receive
        except Exception as e:
            logger.warning(f"Failed to parse request body: {e}")
            request_data = {}
        
        # Extract user context from headers or request data
        user_id = (
            request_data.get('user_id') or 
            http_request.headers.get('X-User-ID') or 
            'anonymous'
        )
        tenant_id = (
            request_data.get('tenant_id') or 
            http_request.headers.get('X-Tenant-ID') or 
            None
        )
        
        # Extract routing_service from request (default to Free if invalid)
        routing_service_raw = request_data.get('routing_service', '')
        if isinstance(routing_service_raw, str):
            routing_service = routing_service_raw.strip().lower()
        else:
            routing_service = 'free'
        
        if routing_service not in ['free', 'paid', 'enterprise']:
            routing_service = 'free'
        
        # Extract policy preferences from request data or headers
        # If not provided, map routing_service to default policy values
        latency_policy = (
            request_data.get('latency_policy') or 
            http_request.headers.get('X-Latency-Policy') or 
            None
        )
        # Convert empty string to None
        if latency_policy == '':
            latency_policy = None
            
        cost_policy = (
            request_data.get('cost_policy') or 
            http_request.headers.get('X-Cost-Policy') or 
            None
        )
        # Convert empty string to None
        if cost_policy == '':
            cost_policy = None
            
        accuracy_policy = (
            request_data.get('accuracy_policy') or 
            http_request.headers.get('X-Accuracy-Policy') or 
            None
        )
        # Convert empty string to None
        if accuracy_policy == '':
            accuracy_policy = None
        
        # Map routing_service to default policy values if not explicitly provided
        # Use defaults based on routing_service if any policy is missing
        logger.info(f"Before mapping - routing_service={routing_service}, latency_policy={latency_policy}, cost_policy={cost_policy}, accuracy_policy={accuracy_policy}")
        if latency_policy is None or cost_policy is None or accuracy_policy is None:
            if routing_service == 'free':
                # Free: high latency, tier_1 cost, sensitive accuracy
                if latency_policy is None:
                    latency_policy = 'high'
                if cost_policy is None:
                    cost_policy = 'tier_1'
                if accuracy_policy is None:
                    accuracy_policy = 'sensitive'
            elif routing_service == 'paid':
                # Paid: medium latency, tier_2 cost, sensitive accuracy
                if latency_policy is None:
                    latency_policy = 'medium'
                if cost_policy is None:
                    cost_policy = 'tier_2'
                if accuracy_policy is None:
                    accuracy_policy = 'sensitive'
            elif routing_service == 'enterprise':
                # Enterprise: low latency, tier_3 cost, standard accuracy
                if latency_policy is None:
                    latency_policy = 'low'
                if cost_policy is None:
                    cost_policy = 'tier_3'
                if accuracy_policy is None:
                    accuracy_policy = 'standard'
        
        logger.info(f"After mapping - routing_service={routing_service}, latency_policy={latency_policy}, cost_policy={cost_policy}, accuracy_policy={accuracy_policy}")
        
        print("=" * 80)
        print("🚀 SMART ROUTER - Processing Request")
        print(f"   Service Type: {service_type}")
        print(f"   User ID: {user_id}")
        print(f"   Tenant ID: {tenant_id}")
        print(f"   Routing Service: {routing_service.upper()}")
        print(f"   Latency Policy: {latency_policy}")
        print(f"   Cost Policy: {cost_policy}")
        print(f"   Accuracy Policy: {accuracy_policy}")
        print("=" * 80)
        
        # Step 1: Call Policy Engine
        policy_response = await get_policy_decision(
            user_id=user_id,
            tenant_id=tenant_id,
            latency_policy=latency_policy,
            cost_policy=cost_policy,
            accuracy_policy=accuracy_policy
        )
        
        # Get service URL and endpoint
        service_url = SERVICE_URL_MAP[service_type]
        endpoint = SERVICE_ENDPOINT_MAP[service_type]
        
        # Map model_family from policy engine to serviceId variant
        # Always use hardcoded base serviceId for TTS service
        base_service_id = "indic-tts-coqui-indo_aryan"
        service_id_variant = None
        
        # Determine serviceId variant based on model_family from policy engine
        if policy_response and 'routing_flags' in policy_response:
            model_family = policy_response['routing_flags'].get('model_family', 'distilled')
            model_family_lower = model_family.lower()
            
            if model_family_lower == 'distilled':
                service_id_variant = f"{base_service_id}_1"
            elif model_family_lower == 'balanced':
                service_id_variant = f"{base_service_id}_2"
            elif model_family_lower in ['state_of_art', 'state_of_the_art', 'state-of-art']:
                service_id_variant = f"{base_service_id}_3"
            else:
                # Default to variant 1 for unknown model_family
                service_id_variant = f"{base_service_id}_1"
            
            print("=" * 80)
            print(f"🔧 SERVICE ID MAPPING")
            print(f"   Routing Service: {routing_service.upper()}")
            print(f"   Model Family: {model_family}")
            print(f"   ServiceId Variant (for reference): {service_id_variant}")
            print(f"   Hardcoded ServiceId for TTS: {base_service_id}")
            print("=" * 80)
        else:
            print("=" * 80)
            print(f"🔧 SERVICE ID MAPPING")
            print(f"   Routing Service: {routing_service.upper()}")
            print(f"   Model Family: N/A (no policy response)")
            print(f"   Using default ServiceId: {base_service_id}")
            print("=" * 80)
        
        # Build payload for target service (preserve original request structure)
        service_payload = {}
        
        # Copy input data (varies by service)
        if 'input' in request_data:
            service_payload['input'] = request_data['input']
        if 'audio' in request_data:
            service_payload['audio'] = request_data['audio']
        
        # Copy config and set hardcoded serviceId
        if 'config' in request_data:
            config = request_data['config'].copy()
        else:
            config = {}
        
        # Always set the hardcoded serviceId for TTS service
        config['serviceId'] = base_service_id
        service_payload['config'] = config
        
        # Print the serviceId being passed to the service
        print("=" * 80)
        print(f"📋 SERVICE ID BEING PASSED TO {service_type.upper()}")
        print(f"   ServiceId: {config.get('serviceId', 'N/A')}")
        print("=" * 80)
        
        # Add controlConfig if present
        if 'controlConfig' in request_data:
            service_payload['controlConfig'] = request_data['controlConfig']
        
        # Forward auth headers
        headers = {}
        auth_header = http_request.headers.get("Authorization")
        if auth_header:
            headers["Authorization"] = auth_header
        
        api_key = http_request.headers.get("X-API-Key")
        if api_key:
            headers["X-API-Key"] = api_key
        
        x_auth_source = http_request.headers.get("X-Auth-Source")
        if x_auth_source:
            headers["X-Auth-Source"] = x_auth_source
        
        # Forward correlation ID
        correlation_id = http_request.headers.get("X-Correlation-ID")
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        
        print("=" * 80)
        print(f"📤 ROUTING TO SERVICE: {service_type.upper()}")
        print(f"   Service URL: {service_url}{endpoint}")
        print(f"   Payload keys: {list(service_payload.keys())}")
        print("=" * 80)
        
        # Step 2: Route to service
        service_response = await route_to_service(
            service_type=service_type,
            service_url=service_url,
            endpoint=endpoint,
            payload=service_payload,
            headers=headers
        )
        
        print("=" * 80)
        print(f"✅ SERVICE RESPONSE RECEIVED")
        print(f"   Service: {service_type.upper()}")
        print(f"   Response keys: {list(service_response.keys()) if isinstance(service_response, dict) else 'N/A'}")
        print("=" * 80)
        
        # Return service response directly (not wrapped)
        return service_response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smart routing failed: {e}", exc_info=True)
        print(f"❌ Smart routing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Smart routing failed: {str(e)}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "smart-router",
        "version": "1.0.0",
        "status": "running",
        "description": "Intelligent routing service for AI4I platform"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERVICE_PORT)
