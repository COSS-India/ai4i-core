"""
Telemetry Service - Process and route telemetry data
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from elasticsearch import AsyncElasticsearch
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Import observability clients and router
from ai4icore_telemetry import OpenSearchQueryClient, JaegerQueryClient
from routers.observability_router import router as observability_router
import casbin

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Telemetry Service",
    version="1.0.0",
    description="Process and route telemetry data for microservices"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Global variables for connections
redis_client = None
db_engine = None
db_session = None
es_client = None

# Observability clients (for querying logs and traces)
opensearch_query_client = None
jaeger_query_client = None
rbac_enforcer = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, es_client
    global opensearch_query_client, jaeger_query_client, rbac_enforcer
    
    try:
        # Initialize Redis connection
        redis_client = redis.from_url(
            f"redis://:{os.getenv('REDIS_PASSWORD', 'redis_secure_password_2024')}@"
            f"{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        )
        await redis_client.ping()
        logger.info("Connected to Redis")
        
        # Initialize PostgreSQL connection
        database_url = os.getenv(
            'DATABASE_URL', 
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/telemetry_db'
        )
        db_engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=5,
            echo=False
        )
        db_session = sessionmaker(
            db_engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
        logger.info("Connected to PostgreSQL")
        
        # Initialize Elasticsearch client
        es_url = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearch:9200')
        es_username = os.getenv('ELASTICSEARCH_USERNAME', 'elastic')
        es_password = os.getenv('ELASTICSEARCH_PASSWORD', 'elastic_secure_password_2024')
        
        es_client = AsyncElasticsearch(
            [es_url],
            basic_auth=(es_username, es_password),
            verify_certs=False
        )
        await es_client.ping()
        logger.info("Connected to Elasticsearch")
        
        # Initialize OpenSearch query client (for observability endpoints)
        opensearch_query_client = OpenSearchQueryClient(
            url=os.getenv("OPENSEARCH_URL", "http://opensearch:9200"),
            username=os.getenv("OPENSEARCH_USERNAME", "admin"),
            password=os.getenv("OPENSEARCH_PASSWORD", "admin"),
            verify_certs=False
        )
        # Set global in router module
        from routers import observability_router
        observability_router.opensearch_client = opensearch_query_client
        logger.info("OpenSearch query client initialized")
        
        # Initialize Jaeger query client (for observability endpoints)
        jaeger_query_client = JaegerQueryClient(
            url=os.getenv("JAEGER_QUERY_URL", "http://jaeger:16686")
        )
        observability_router.jaeger_client = jaeger_query_client
        logger.info("Jaeger query client initialized")
        
        # Initialize Casbin enforcer for RBAC
        casbin_model_path = os.path.join(os.path.dirname(__file__), "casbin_model.conf")
        if not os.path.exists(casbin_model_path):
            # Use default model if not found
            rbac_enforcer = casbin.Enforcer()
            logger.warning("Casbin model file not found, using default model")
        else:
            rbac_enforcer = casbin.Enforcer(casbin_model_path)
            logger.info("Casbin enforcer initialized")
        
        # Load policies from database
        # Try to connect to auth database (where roles/permissions are stored)
        try:
            from sqlalchemy import text
            
            # Try auth database first (where roles/permissions are stored)
            auth_db_url = os.getenv(
                'AUTH_DATABASE_URL',
                'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/dhruva_db'
            )
            auth_db_engine = create_async_engine(auth_db_url, echo=False)
            auth_db_session = sessionmaker(auth_db_engine, class_=AsyncSession, expire_on_commit=False)
            
            async with auth_db_session() as session:
                # Load role-permission policies
                result = await session.execute(
                    text("""
                        SELECT r.name, p.resource, p.action
                        FROM roles r
                        JOIN role_permissions rp ON r.id = rp.role_id
                        JOIN permissions p ON p.id = rp.permission_id
                    """)
                )
                role_perms = result.all()
                tenant = "default"
                
                for role_name, resource, action in role_perms:
                    sub = f"role:{role_name}"
                    rbac_enforcer.add_policy(sub, tenant, resource, action)
                
                # Load user-role mappings
                user_role_result = await session.execute(
                    text("""
                        SELECT ur.user_id, r.name
                        FROM user_roles ur
                        JOIN roles r ON r.id = ur.role_id
                    """)
                )
                user_roles = user_role_result.all()
                
                for user_id, role_name in user_roles:
                    user_sub = f"user:{user_id}"
                    role_sub = f"role:{role_name}"
                    rbac_enforcer.add_grouping_policy(user_sub, role_sub, tenant)
                
                logger.info(f"Loaded {len(role_perms)} role-permission policies and {len(user_roles)} user-role mappings into Casbin")
                await auth_db_engine.dispose()
        except Exception as e:
            logger.warning(f"Failed to load Casbin policies from database: {e}")
            logger.warning("Adding default policies for testing...")
            # Add default policies for ADMIN, MODERATOR, and USER roles (for testing)
            tenant = "default"
            
            # ADMIN role permissions
            rbac_enforcer.add_policy("role:ADMIN", tenant, "logs", "read")
            rbac_enforcer.add_policy("role:ADMIN", tenant, "traces", "read")
            
            # MODERATOR role permissions
            rbac_enforcer.add_policy("role:MODERATOR", tenant, "logs", "read")
            rbac_enforcer.add_policy("role:MODERATOR", tenant, "traces", "read")
            
            # USER role permissions
            rbac_enforcer.add_policy("role:USER", tenant, "logs", "read")
            rbac_enforcer.add_policy("role:USER", tenant, "traces", "read")
            
            # Map some test users to roles (optional - JWT already contains roles)
            # These are just for direct user-role mapping if needed
            rbac_enforcer.add_grouping_policy("user:2", "role:ADMIN", tenant)
            rbac_enforcer.add_grouping_policy("user:101", "role:USER", tenant)
            
            logger.info("Added default policies for ADMIN, MODERATOR, and USER roles for testing")
        
        # Set global in router module
        observability_router.rbac_enforcer = rbac_enforcer
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, es_client
    global opensearch_query_client, jaeger_query_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if es_client:
        await es_client.close()
        logger.info("Elasticsearch connection closed")
    
    if opensearch_query_client:
        await opensearch_query_client.close()
        logger.info("OpenSearch query client closed")
    
    if jaeger_query_client:
        await jaeger_query_client.close()
        logger.info("Jaeger query client closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Telemetry Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Process and route telemetry data for microservices"
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
        
        # Check PostgreSQL connectivity
        if db_engine:
            try:
                from sqlalchemy import text
                async with db_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                postgres_status = "healthy"
            except Exception as e:
                logger.warning(f"PostgreSQL health check failed: {e}")
                postgres_status = "unhealthy"
        else:
            postgres_status = "unhealthy"
        
        # Check Elasticsearch connectivity
        if es_client:
            try:
                await es_client.ping()
                elasticsearch_status = "healthy"
            except:
                elasticsearch_status = "unhealthy"
        else:
            elasticsearch_status = "unhealthy"
        
        overall_status = "healthy" if all([
            redis_status == "healthy", 
            postgres_status == "healthy",
            elasticsearch_status == "healthy"
        ]) else "unhealthy"
        
        return {
            "status": overall_status,
            "service": "telemetry-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "elasticsearch": elasticsearch_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/telemetry/status")
async def telemetry_status():
    """Telemetry service status"""
    return {
        "service": "telemetry-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "Log aggregation and processing",
            "Distributed tracing",
            "Event correlation",
            "Data enrichment and contextualization"
        ]
    }

@app.post("/api/v1/telemetry/logs")
async def ingest_log():
    """Ingest log entry"""
    return {"message": "Log ingestion - to be implemented"}

@app.post("/api/v1/telemetry/traces")
async def ingest_trace():
    """Ingest trace data"""
    return {"message": "Trace ingestion - to be implemented"}

@app.get("/api/v1/telemetry/logs/search")
async def search_logs():
    """Search logs"""
    return {"message": "Log search - to be implemented"}

@app.get("/api/v1/telemetry/traces/search")
async def search_traces():
    """Search traces"""
    return {"message": "Trace search - to be implemented"}

# Register observability router
app.include_router(
    observability_router,
    prefix="/api/v1/observability",
    tags=["Observability"]
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)
