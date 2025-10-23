"""
API Gateway Service - Central entry point for all microservice requests
"""
import os
import asyncio
import logging
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, Request, HTTPException, Response
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import redis.asyncio as redis
import httpx
from auth_middleware import auth_middleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for ASR endpoints
class AudioInput(BaseModel):
    """Audio input for ASR processing."""
    audioContent: Optional[str] = Field(None, description="Base64 encoded audio content")
    audioUri: Optional[str] = Field(None, description="URI to audio file")

class LanguageConfig(BaseModel):
    """Language configuration for ASR."""
    sourceLanguage: str = Field(..., description="Source language code (e.g., 'en', 'hi')")

class ASRInferenceConfig(BaseModel):
    """Configuration for ASR inference."""
    serviceId: str = Field(..., description="ASR service/model ID")
    language: LanguageConfig = Field(..., description="Language configuration")
    audioFormat: str = Field(default="wav", description="Audio format")
    samplingRate: int = Field(default=16000, description="Audio sampling rate")
    transcriptionFormat: str = Field(default="transcript", description="Output format")
    bestTokenCount: int = Field(default=0, description="Number of best token alternatives")

class ASRInferenceRequest(BaseModel):
    """ASR inference request model."""
    audio: List[AudioInput] = Field(..., description="List of audio inputs", min_items=1)
    config: ASRInferenceConfig = Field(..., description="Inference configuration")
    controlConfig: Optional[Dict[str, Any]] = Field(None, description="Additional control parameters")

class TranscriptOutput(BaseModel):
    """Transcription output."""
    source: str = Field(..., description="Transcribed text")

class ASRInferenceResponse(BaseModel):
    """ASR inference response model."""
    output: List[TranscriptOutput] = Field(..., description="Transcription results")
    config: Optional[Dict[str, Any]] = Field(None, description="Response metadata")

class StreamingInfo(BaseModel):
    """Streaming service information."""
    endpoint: str = Field(..., description="WebSocket endpoint URL")
    supported_formats: List[str] = Field(..., description="Supported audio formats")
    max_connections: int = Field(..., description="Maximum concurrent connections")
    response_frequency_ms: int = Field(..., description="Response frequency in milliseconds")

class ServiceRegistry:
    """Redis-based service instance management"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.service_ttl = int(os.getenv('SERVICE_REGISTRY_TTL', '300'))
    
    async def register_service(self, service_name: str, instance_id: str, url: str) -> None:
        """Register a service instance"""
        instance_data = {
            'instance_id': instance_id,
            'url': url,
            'health_status': 'healthy',  # Mark as healthy by default
            'last_check_timestamp': str(int(time.time())),
            'avg_response_time': '0.0',
            'consecutive_failures': '0'
        }
        
        # Store instance data
        await self.redis.hset(f"service:{service_name}:instances", instance_id, str(instance_data))
        
        # Add to active instances sorted set (scored by response time)
        await self.redis.zadd(f"service:{service_name}:active", {instance_id: 0.0})
        
        # Set TTL
        await self.redis.expire(f"service:{service_name}:instances", self.service_ttl)
        await self.redis.expire(f"service:{service_name}:active", self.service_ttl)
        
        logger.info(f"Registered service instance: {service_name}:{instance_id} -> {url}")
    
    async def update_health(self, service_name: str, instance_id: str, is_healthy: bool, response_time: float) -> None:
        """Update health status and response time for an instance"""
        instance_key = f"service:{service_name}:instances"
        
        # Get current instance data
        instance_data_raw = await self.redis.hget(instance_key, instance_id)
        if not instance_data_raw:
            return
        
        # Parse and update instance data
        instance_data = eval(instance_data_raw.decode()) if isinstance(instance_data_raw, bytes) else instance_data_raw
        instance_data['health_status'] = 'healthy' if is_healthy else 'unhealthy'
        instance_data['last_check_timestamp'] = str(int(time.time()))
        
        if is_healthy:
            # Update average response time (simple moving average)
            current_avg = float(instance_data.get('avg_response_time', 0.0))
            new_avg = (current_avg + response_time) / 2
            instance_data['avg_response_time'] = str(new_avg)
            instance_data['consecutive_failures'] = '0'
            
            # Update active instances sorted set
            await self.redis.zadd(f"service:{service_name}:active", {instance_id: new_avg})
        else:
            # Increment consecutive failures
            failures = int(instance_data.get('consecutive_failures', 0)) + 1
            instance_data['consecutive_failures'] = str(failures)
            
            # Remove from active instances if too many failures
            max_failures = int(os.getenv('MAX_CONSECUTIVE_FAILURES', '3'))
            if failures >= max_failures:
                await self.redis.zrem(f"service:{service_name}:active", instance_id)
                logger.warning(f"Instance {instance_id} removed from active pool due to {failures} consecutive failures")
        
        # Update instance data
        await self.redis.hset(instance_key, instance_id, str(instance_data))
    
    async def get_healthy_instances(self, service_name: str) -> List[Tuple[str, str]]:
        """Get healthy instances sorted by response time (best first)"""
        active_instances = await self.redis.zrange(f"service:{service_name}:active", 0, -1, withscores=True)
        instances = []
        
        for instance_id, score in active_instances:
            instance_data_raw = await self.redis.hget(f"service:{service_name}:instances", instance_id)
            if instance_data_raw:
                instance_data = eval(instance_data_raw.decode()) if isinstance(instance_data_raw, bytes) else instance_data_raw
                if instance_data.get('health_status') == 'healthy':
                    instances.append((instance_id, instance_data['url']))
        
        return instances
    
    async def remove_instance(self, service_name: str, instance_id: str) -> None:
        """Remove an instance from the registry"""
        await self.redis.hdel(f"service:{service_name}:instances", instance_id)
        await self.redis.zrem(f"service:{service_name}:active", instance_id)
        logger.info(f"Removed instance: {service_name}:{instance_id}")

class LoadBalancer:
    """Health-aware instance selection with weighted round-robin"""
    
    def __init__(self, service_registry: ServiceRegistry):
        self.registry = service_registry
        self.algorithm = os.getenv('LOAD_BALANCER_ALGORITHM', 'weighted_round_robin')
    
    async def select_instance(self, service_name: str) -> Optional[Tuple[str, str]]:
        """Select the best available instance for a service"""
        instances = await self.registry.get_healthy_instances(service_name)
        
        if not instances:
            logger.warning(f"No healthy instances available for service: {service_name}")
            return None
        
        if self.algorithm == 'weighted_round_robin':
            # Return the instance with the lowest response time (best score)
            return instances[0]
        elif self.algorithm == 'random':
            import random
            return random.choice(instances)
        else:
            # Default to first available
            return instances[0]

class RouteManager:
    """Path-to-service mapping management"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.routes = {
            '/api/v1/auth': 'auth-service',
            '/api/v1/config': 'config-service',
            '/api/v1/feature-flags': 'config-service',
            '/api/v1/metrics': 'metrics-service',
            '/api/v1/telemetry': 'telemetry-service',
            '/api/v1/alerting': 'alerting-service',
            '/api/v1/dashboard': 'dashboard-service',
            '/api/v1/asr': 'asr-service',
            '/api/v1/tts': 'tts-service',
            '/api/v1/nmt': 'nmt-service'
        }
    
    async def get_service_for_path(self, path: str) -> Optional[str]:
        """Get service name for a given path using longest prefix matching"""
        # Sort routes by length (longest first) for proper prefix matching
        sorted_routes = sorted(self.routes.items(), key=lambda x: len(x[0]), reverse=True)
        
        for route_prefix, service_name in sorted_routes:
            if path.startswith(route_prefix):
                return service_name
        
        return None
    
    async def load_routes_from_redis(self) -> None:
        """Load route mappings from Redis"""
        try:
            route_data = await self.redis.hgetall("routes:mappings")
            if route_data:
                self.routes = {k.decode(): v.decode() for k, v in route_data.items()}
                logger.info(f"Loaded {len(self.routes)} routes from Redis")
        except Exception as e:
            logger.warning(f"Failed to load routes from Redis: {e}")

# Initialize FastAPI app
app = FastAPI(
    title="API Gateway Service",
    version="1.0.0",
    description="Central entry point for all microservice requests"
)

# Global variables for connections and components
redis_client = None
http_client = None
service_registry = None
load_balancer = None
route_manager = None
health_monitor_task = None

# Utility functions
def generate_correlation_id() -> str:
    """Generate a new correlation ID"""
    return str(uuid.uuid4())

def is_hop_by_hop_header(header_name: str) -> bool:
    """Check if header is hop-by-hop and should not be forwarded"""
    hop_by_hop_headers = {
        'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
        'te', 'trailers', 'transfer-encoding', 'upgrade'
    }
    return header_name.lower() in hop_by_hop_headers

def prepare_forwarding_headers(request: Request, correlation_id: str, request_id: str) -> Dict[str, str]:
    """Prepare headers for forwarding to downstream services"""
    headers = {}
    
    # Copy all incoming headers except hop-by-hop headers
    for header_name, header_value in request.headers.items():
        if not is_hop_by_hop_header(header_name):
            headers[header_name] = header_value
    
    # Add forwarding headers
    headers['X-Forwarded-For'] = request.client.host if request.client else 'unknown'
    headers['X-Forwarded-Proto'] = request.url.scheme
    headers['X-Forwarded-Host'] = request.headers.get('host', 'unknown')
    headers['X-Correlation-ID'] = correlation_id
    headers['X-Request-ID'] = request_id
    headers['X-Gateway-Timestamp'] = str(int(time.time() * 1000))
    
    return headers

def log_request(method: str, path: str, service: str, instance: str, duration: float, status_code: int) -> None:
    """Log request details for observability"""
    logger.info(
        f"Request: {method} {path} -> {service}:{instance} "
        f"({duration:.3f}s, {status_code})"
    )

async def health_monitor():
    """Background task to monitor health of all service instances"""
    global service_registry, http_client
    
    if not service_registry or not http_client:
        logger.error("Health monitor: service registry or HTTP client not initialized")
        return
    
    health_check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))
    health_check_timeout = int(os.getenv('HEALTH_CHECK_TIMEOUT', '5'))
    
    logger.info(f"Starting health monitor (interval: {health_check_interval}s)")
    
    while True:
        try:
            # Get all registered services
            service_keys = await redis_client.keys("service:*:instances")
            
            for service_key in service_keys:
                service_name = service_key.decode().split(':')[1]
                
                # Get ALL instances for this service (not just healthy ones)
                all_instances = await redis_client.hgetall(f"service:{service_name}:instances")
                
                for instance_id_bytes, instance_data_bytes in all_instances.items():
                    instance_id = instance_id_bytes.decode() if isinstance(instance_id_bytes, bytes) else instance_id_bytes
                    instance_data_raw = instance_data_bytes.decode() if isinstance(instance_data_bytes, bytes) else instance_data_bytes
                    
                    try:
                        # Parse instance data
                        instance_data = eval(instance_data_raw) if isinstance(instance_data_raw, str) else instance_data_raw
                        instance_url = instance_data.get('url')
                        
                        if not instance_url:
                            continue
                            
                        # Perform health check
                        start_time = time.time()
                        response = await http_client.get(
                            f"{instance_url}/health",
                            timeout=health_check_timeout
                        )
                        response_time = time.time() - start_time
                        
                        is_healthy = response.status_code == 200
                        
                        # Update health status
                        await service_registry.update_health(
                            service_name, instance_id, is_healthy, response_time
                        )
                        
                        if is_healthy:
                            logger.debug(f"Health check passed: {service_name}:{instance_id} ({response_time:.3f}s)")
                        else:
                            logger.warning(f"Health check failed: {service_name}:{instance_id} (status: {response.status_code})")
                            
                    except Exception as e:
                        # Health check failed
                        await service_registry.update_health(
                            service_name, instance_id, False, 0.0
                        )
                        logger.warning(f"Health check error: {service_name}:{instance_id} - {e}")
            
            # Wait for next health check cycle
            await asyncio.sleep(health_check_interval)
            
        except Exception as e:
            logger.error(f"Health monitor error: {e}")
            await asyncio.sleep(health_check_interval)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Global variables for connections and components
redis_client = None
http_client = None
service_registry = None
load_balancer = None
route_manager = None
health_monitor_task = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections and components on startup"""
    global redis_client, http_client, service_registry, load_balancer, route_manager, health_monitor_task
    
    try:
        # Initialize Redis connection
        redis_password = os.getenv('REDIS_PASSWORD', 'redis_secure_password_2024')
        if redis_password and redis_password != 'none':
            redis_url = f"redis://:{redis_password}@{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        else:
            redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        
        redis_client = redis.from_url(redis_url)
        await redis_client.ping()
        logger.info("Connected to Redis")
        
        # Initialize HTTP client
        http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("HTTP client initialized")
        
        # Initialize components
        service_registry = ServiceRegistry(redis_client)
        load_balancer = LoadBalancer(service_registry)
        route_manager = RouteManager(redis_client)
        
        # Load routes from Redis
        await route_manager.load_routes_from_redis()
        
        # Register all downstream services
        services = {
            'auth-service': os.getenv('AUTH_SERVICE_URL', 'http://auth-service:8081'),
            'config-service': os.getenv('CONFIG_SERVICE_URL', 'http://config-service:8082'),
            'metrics-service': os.getenv('METRICS_SERVICE_URL', 'http://metrics-service:8083'),
            'telemetry-service': os.getenv('TELEMETRY_SERVICE_URL', 'http://telemetry-service:8084'),
            'alerting-service': os.getenv('ALERTING_SERVICE_URL', 'http://alerting-service:8085'),
            'dashboard-service': os.getenv('DASHBOARD_SERVICE_URL', 'http://dashboard-service:8086'),
            'asr-service': os.getenv('ASR_SERVICE_URL', 'http://asr-service:8087'),
            'tts-service': os.getenv('TTS_SERVICE_URL', 'http://tts-service:8088'),
            'nmt-service': os.getenv('NMT_SERVICE_URL', 'http://nmt-service:8089')
        }
        
        for service_name, service_url in services.items():
            instance_id = f"{service_name}-1"
            await service_registry.register_service(service_name, instance_id, service_url)
        
        # Start health monitoring background task
        health_monitor_task = asyncio.create_task(health_monitor())
        
        logger.info("API Gateway initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize API Gateway: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections and tasks on shutdown"""
    global redis_client, http_client, health_monitor_task
    
    # Cancel health monitoring task
    if health_monitor_task:
        health_monitor_task.cancel()
        try:
            await health_monitor_task
        except asyncio.CancelledError:
            pass
        logger.info("Health monitor task cancelled")
    
    # Close connections
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "API Gateway Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Central entry point for all microservice requests"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker health checks"""
    try:
        # Check Redis connectivity
        if redis_client:
            await redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "unhealthy"
        
        return {
            "status": "healthy",
            "service": "api-gateway-service",
            "redis": redis_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/status")
async def api_status():
    """API status endpoint"""
    return {
        "api_version": "v1",
        "status": "operational",
        "services": {
            "auth": os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081"),
            "config": os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082"),
            "metrics": os.getenv("METRICS_SERVICE_URL", "http://metrics-service:8083"),
            "telemetry": os.getenv("TELEMETRY_SERVICE_URL", "http://telemetry-service:8084"),
            "alerting": os.getenv("ALERTING_SERVICE_URL", "http://alerting-service:8085"),
            "dashboard": os.getenv("DASHBOARD_SERVICE_URL", "http://dashboard-service:8086"),
            "asr": os.getenv("ASR_SERVICE_URL", "http://asr-service:8087"),
            "tts": os.getenv("TTS_SERVICE_URL", "http://tts-service:8088"),
            "nmt": os.getenv("NMT_SERVICE_URL", "http://nmt-service:8089")
        }
    }

# Authentication Endpoints (Proxy to Auth Service)

@app.post("/api/v1/auth/register")
async def register_user(request: Request):
    """Register a new user"""
    return await proxy_to_auth_service(request, "/api/v1/auth/register")

@app.post("/api/v1/auth/login")
async def login_user(request: Request):
    """Login user"""
    return await proxy_to_auth_service(request, "/api/v1/auth/login")

@app.post("/api/v1/auth/logout")
async def logout_user(request: Request):
    """Logout user"""
    return await proxy_to_auth_service(request, "/api/v1/auth/logout")

@app.post("/api/v1/auth/refresh")
async def refresh_token(request: Request):
    """Refresh access token"""
    return await proxy_to_auth_service(request, "/api/v1/auth/refresh")

@app.get("/api/v1/auth/validate")
async def validate_token(request: Request):
    """Validate token"""
    return await proxy_to_auth_service(request, "/api/v1/auth/validate")

@app.get("/api/v1/auth/me")
async def get_current_user(request: Request):
    """Get current user info"""
    return await proxy_to_auth_service(request, "/api/v1/auth/me")

@app.put("/api/v1/auth/me")
async def update_current_user(request: Request):
    """Update current user info"""
    return await proxy_to_auth_service(request, "/api/v1/auth/me")

@app.post("/api/v1/auth/change-password")
async def change_password(request: Request):
    """Change password"""
    return await proxy_to_auth_service(request, "/api/v1/auth/change-password")

@app.post("/api/v1/auth/request-password-reset")
async def request_password_reset(request: Request):
    """Request password reset"""
    return await proxy_to_auth_service(request, "/api/v1/auth/request-password-reset")

@app.post("/api/v1/auth/reset-password")
async def reset_password(request: Request):
    """Reset password"""
    return await proxy_to_auth_service(request, "/api/v1/auth/reset-password")

@app.get("/api/v1/auth/api-keys")
async def list_api_keys(request: Request):
    """List API keys"""
    return await proxy_to_auth_service(request, "/api/v1/auth/api-keys")

@app.post("/api/v1/auth/api-keys")
async def create_api_key(request: Request):
    """Create API key"""
    return await proxy_to_auth_service(request, "/api/v1/auth/api-keys")

@app.delete("/api/v1/auth/api-keys/{key_id}")
async def revoke_api_key(request: Request, key_id: int):
    """Revoke API key"""
    return await proxy_to_auth_service(request, f"/api/v1/auth/api-keys/{key_id}")

@app.get("/api/v1/auth/oauth2/providers")
async def get_oauth2_providers(request: Request):
    """Get OAuth2 providers"""
    return await proxy_to_auth_service(request, "/api/v1/auth/oauth2/providers")

@app.post("/api/v1/auth/oauth2/callback")
async def oauth2_callback(request: Request):
    """OAuth2 callback"""
    return await proxy_to_auth_service(request, "/api/v1/auth/oauth2/callback")

    # ASR Service Endpoints (Proxy to ASR Service)

@app.post("/api/v1/asr/transcribe", response_model=ASRInferenceResponse)
async def transcribe_audio(request: ASRInferenceRequest):
    """Transcribe audio to text using ASR service (alias for /inference)"""
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(request.dict()).encode()
    return await proxy_to_service(None, "/api/v1/asr/inference", "asr-service", method="POST", body=body)

@app.post("/api/v1/asr/inference", response_model=ASRInferenceResponse)
async def asr_inference(request: ASRInferenceRequest):
    """Perform batch ASR inference on audio inputs"""
    import json
    # Convert Pydantic model to JSON for proxy
    body = json.dumps(request.dict()).encode()
    return await proxy_to_service(None, "/api/v1/asr/inference", "asr-service", method="POST", body=body)

@app.get("/api/v1/asr/streaming/info", response_model=StreamingInfo)
async def get_streaming_info():
    """Get WebSocket streaming endpoint information"""
    return await proxy_to_service(None, "/streaming/info", "asr-service")

@app.get("/api/v1/asr/models")
async def get_asr_models():
    """Get available ASR models"""
    return await proxy_to_service(None, "/api/v1/asr/models", "asr-service")

@app.get("/api/v1/asr/health")
async def asr_health(request: Request):
    """ASR service health check"""
    return await proxy_to_service(request, "/health", "asr-service")

# TTS Service Endpoints (Proxy to TTS Service)

@app.post("/api/v1/tts/synthesize")
async def synthesize_speech(request: Request):
    """Synthesize text to speech using TTS service"""
    return await proxy_to_service(request, "/api/v1/tts/synthesize", "tts-service")

@app.post("/api/v1/tts/stream")
async def stream_synthesize(request: Request):
    """Stream text-to-speech synthesis using TTS service"""
    return await proxy_to_service(request, "/api/v1/tts/stream", "tts-service")

@app.get("/api/v1/tts/voices")
async def get_tts_voices(request: Request):
    """Get available TTS voices"""
    return await proxy_to_service(request, "/api/v1/tts/voices", "tts-service")

@app.get("/api/v1/tts/health")
async def tts_health(request: Request):
    """TTS service health check"""
    return await proxy_to_service(request, "/api/v1/tts/health", "tts-service")

# NMT Service Endpoints (Proxy to NMT Service)

@app.post("/api/v1/nmt/translate")
async def translate_text(request: Request):
    """Translate text using NMT service"""
    return await proxy_to_service(request, "/api/v1/nmt/translate", "nmt-service")

@app.post("/api/v1/nmt/batch-translate")
async def batch_translate(request: Request):
    """Batch translate multiple texts using NMT service"""
    return await proxy_to_service(request, "/api/v1/nmt/batch-translate", "nmt-service")

@app.get("/api/v1/nmt/languages")
async def get_nmt_languages(request: Request):
    """Get supported languages for NMT service"""
    return await proxy_to_service(request, "/api/v1/nmt/languages", "nmt-service")

@app.get("/api/v1/nmt/health")
async def nmt_health(request: Request):
    """NMT service health check"""
    return await proxy_to_service(request, "/api/v1/nmt/health", "nmt-service")

# Protected Endpoints (Require Authentication)

@app.get("/api/v1/protected/status")
async def protected_status(request: Request):
    """Protected status endpoint"""
    user = await auth_middleware.require_auth(request)
    return {
        "message": "This is a protected endpoint",
        "user": user,
        "timestamp": time.time()
    }

@app.get("/api/v1/protected/profile")
async def get_user_profile(request: Request):
    """Get user profile (requires authentication)"""
    user = await auth_middleware.require_auth(request)
    return {
        "user_id": user.get("user_id"),
        "username": user.get("username"),
        "permissions": user.get("permissions", []),
        "message": "User profile data would be fetched here"
    }

# Helper function to proxy requests to auth service
async def proxy_to_auth_service(request: Request, path: str):
    """Proxy request to auth service"""
    auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
    
    try:
        # Prepare request body
        body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            body = await request.body()
        
        # Forward request to auth service
        response = await http_client.request(
            method=request.method,
            url=f"{auth_service_url}{path}",
            headers=dict(request.headers),
            params=request.query_params,
            content=body,
            timeout=30.0
        )
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type')
        )
        
    except Exception as e:
        logger.error(f"Error proxying to auth service: {e}")
        raise HTTPException(status_code=500, detail="Auth service temporarily unavailable")

# Helper function to proxy requests to any service
async def proxy_to_service(request: Optional[Request], path: str, service_name: str, method: str = "GET", body: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None):
    """Proxy request to any service using the load balancer"""
    global service_registry, load_balancer, http_client
    
    try:
        # Select healthy instance
        instance_info = await load_balancer.select_instance(service_name)
        if not instance_info:
            raise HTTPException(status_code=503, detail=f"No healthy instances available for service: {service_name}")
        
        instance_id, instance_url = instance_info
        
        # Prepare request body and headers
        if request is not None:
            method = request.method
            if method in ['POST', 'PUT', 'PATCH']:
                body = await request.body()
            headers = dict(request.headers)
            params = request.query_params
        else:
            params = {}
            if headers is None:
                headers = {}
        
        # Forward request to service
        response = await http_client.request(
            method=method,
            url=f"{instance_url}{path}",
            headers=headers,
            params=params,
            content=body,
            timeout=30.0
        )
        
        # Update health status
        await service_registry.update_health(service_name, instance_id, True, 0.0)
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type')
        )
        
    except Exception as e:
        logger.error(f"Error proxying to {service_name}: {e}")
        raise HTTPException(status_code=500, detail=f"{service_name} temporarily unavailable")

@app.api_route("/{path:path}", methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
async def proxy_request(request: Request, path: str):
    """Catch-all route handler for request forwarding"""
    global service_registry, load_balancer, route_manager, http_client
    
    start_time = time.time()
    correlation_id = request.headers.get('X-Correlation-ID', generate_correlation_id())
    request_id = generate_correlation_id()
    
    try:
        # Determine target service
        service_name = await route_manager.get_service_for_path(f"/{path}")
        if not service_name:
            raise HTTPException(status_code=404, detail=f"No service found for path: /{path}")
        
        # Select healthy instance
        instance_info = await load_balancer.select_instance(service_name)
        if not instance_info:
            raise HTTPException(status_code=503, detail=f"No healthy instances available for service: {service_name}")
        
        instance_id, instance_url = instance_info
        
        # Prepare forwarding headers
        headers = prepare_forwarding_headers(request, correlation_id, request_id)
        
        # Prepare request body
        body = None
        if request.method in ['POST', 'PUT', 'PATCH']:
            body = await request.body()
        
        # Forward request
        response = await http_client.request(
            method=request.method,
            url=f"{instance_url}/{path}",
            headers=headers,
            params=request.query_params,
            content=body,
            timeout=30.0
        )
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Update load balancer metrics
        await service_registry.update_health(service_name, instance_id, True, response_time)
        
        # Log request
        log_request(request.method, f"/{path}", service_name, instance_id, response_time, response.status_code)
        
        # Prepare response headers
        response_headers = {}
        for header_name, header_value in response.headers.items():
            if not is_hop_by_hop_header(header_name):
                response_headers[header_name] = header_value
        
        # Add correlation headers to response
        response_headers['X-Correlation-ID'] = correlation_id
        response_headers['X-Request-ID'] = request_id
        
        # Return response
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response.headers.get('content-type')
        )
        
    except httpx.HTTPStatusError as e:
        response_time = time.time() - start_time
        logger.error(f"HTTP error forwarding request: {e}")
        
        # Update health status for the instance
        if 'instance_id' in locals() and 'service_name' in locals():
            await service_registry.update_health(service_name, instance_id, False, response_time)
        
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
        
    except httpx.RequestError as e:
        response_time = time.time() - start_time
        logger.error(f"Request error forwarding request: {e}")
        
        # Update health status for the instance
        if 'instance_id' in locals() and 'service_name' in locals():
            await service_registry.update_health(service_name, instance_id, False, response_time)
        
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        
    except Exception as e:
        response_time = time.time() - start_time
        logger.error(f"Unexpected error forwarding request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
