"""
Configuration Management Service - Centralized configuration and feature flags
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
from aiokafka import AIOKafkaProducer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Configuration Management Service",
    version="1.0.0",
    description="Centralized configuration and feature flags for microservices"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for connections
redis_client = None
db_engine = None
db_session = None
kafka_producer = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, kafka_producer
    
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
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/config_db'
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
        
        # Initialize Kafka producer
        kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
        kafka_producer = AIOKafkaProducer(
            bootstrap_servers=kafka_servers,
            value_serializer=lambda v: str(v).encode('utf-8')
        )
        await kafka_producer.start()
        logger.info("Connected to Kafka")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, kafka_producer
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if kafka_producer:
        await kafka_producer.stop()
        logger.info("Kafka producer closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Configuration Management Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Centralized configuration and feature flags for microservices"
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
            async with db_engine.begin() as conn:
                await conn.execute("SELECT 1")
            postgres_status = "healthy"
        else:
            postgres_status = "unhealthy"
        
        # Check Kafka connectivity
        if kafka_producer:
            kafka_status = "healthy"
        else:
            kafka_status = "unhealthy"
        
        overall_status = "healthy" if all([
            redis_status == "healthy", 
            postgres_status == "healthy",
            kafka_status == "healthy"
        ]) else "unhealthy"
        
        return {
            "status": overall_status,
            "service": "config-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "kafka": kafka_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/config/status")
async def config_status():
    """Configuration service status"""
    return {
        "service": "config-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "Environment-specific configurations",
            "Feature flags",
            "Service discovery",
            "Dynamic configuration updates",
            "Configuration audit logging"
        ]
    }

@app.get("/api/v1/config/{key}")
async def get_config(key: str, environment: str = "development"):
    """Get configuration value"""
    return {"key": key, "environment": environment, "message": "Configuration retrieval - to be implemented"}

@app.post("/api/v1/config")
async def set_config():
    """Set configuration value"""
    return {"message": "Configuration setting - to be implemented"}

@app.get("/api/v1/feature-flags")
async def get_feature_flags():
    """Get feature flags"""
    return {"message": "Feature flags retrieval - to be implemented"}

@app.post("/api/v1/feature-flags")
async def set_feature_flag():
    """Set feature flag"""
    return {"message": "Feature flag setting - to be implemented"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
