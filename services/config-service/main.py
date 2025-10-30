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
from models.database_models import Base

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
registry_client = None

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

        # Create tables if they do not exist
        try:
            async with db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
        
        # Initialize Kafka producer (optional)
        try:
            kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
            kafka_producer = AIOKafkaProducer(
                bootstrap_servers=kafka_servers
            )
            await kafka_producer.start()
            logger.info("Connected to Kafka")
        except Exception as kafka_exc:
            kafka_producer = None
            logger.warning(f"Kafka unavailable: {kafka_exc}")
        
        # Initialize ZooKeeper registry client
        from registry.zookeeper_client import ZooKeeperRegistryClient
        global registry_client
        registry_client = ZooKeeperRegistryClient()
        try:
            await registry_client.connect()
            logger.info("Connected to ZooKeeper")
            # Register this service
            service_name = os.getenv('SERVICE_NAME', 'config-service')
            service_port = os.getenv('SERVICE_PORT', '8082')
            instance_id = os.getenv('SERVICE_INSTANCE_ID', f"{service_name}-1")
            service_metadata = {"instance_id": instance_id}
            service_url = f"http://{service_name}:{service_port}"
            health_url = f"{service_url}/health"
            try:
                await registry_client.register_service(service_name, service_url, {"instance_id": instance_id, "health_check_url": health_url, "status": "healthy"})
            except Exception as e:
                logger.warning(f"Failed to register service in ZooKeeper: {e}")
        except Exception as e:
            logger.warning(f"ZooKeeper connection failed: {e}")
        
    except Exception as e:
        logger.error(f"Failed to initialize essential connections: {e}")
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

    if registry_client:
        try:
            service_name = os.getenv('SERVICE_NAME', 'config-service')
            instance_id = os.getenv('SERVICE_INSTANCE_ID', f"{service_name}-1")
            await registry_client.deregister_service(service_name, instance_id)
        except Exception:
            pass
        try:
            await registry_client.disconnect()
        except Exception:
            pass

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Configuration Management Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Centralized configuration and feature flags for microservices"
    }

from routers import config_router, feature_flag_router, service_registry_router, health_router
app.include_router(config_router)
app.include_router(feature_flag_router)
app.include_router(service_registry_router)
app.include_router(health_router)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
