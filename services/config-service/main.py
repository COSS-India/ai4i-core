"""
Configuration Management Service - Centralized configuration
"""
import asyncio
import logging
from ai4icore_env import app_env
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException
import redis.asyncio as redis
from utils.health_status_cache import cache_health_snapshots
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from aiokafka import AIOKafkaProducer
from models.database_models import (
    Base,
    Configuration,
    ServiceRegistry,
    ConfigurationHistory,
) 

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Configuration Management Service",
    version="1.0.0",
    description="Centralized configuration for microservices"
)

# CORS is handled at the nginx gateway, not here.

# Global variables for connections
redis_client = None
db_engine = None
db_session = None
kafka_producer = None
registry_client = None
health_monitor_service = None
health_monitor_task = None

async def periodic_health_check():
    """Background task for periodic health checks"""
    global health_monitor_service, registry_client, db_session, redis_client
    
    if not health_monitor_service:
        logger.warning("Health monitor service not initialized, skipping periodic checks")
        return
    
    health_check_interval = app_env.service_health_check_interval
    additional_endpoints = app_env.health_check_additional_endpoints.split(",")
    additional_endpoints = [e.strip() for e in additional_endpoints if e.strip()]
    
    logger.info(
        f"Starting periodic health check monitor "
        f"(interval: {health_check_interval}s, additional endpoints: {additional_endpoints})"
    )
    
    while True:
        try:
            # Get function to retrieve service instances
            async def get_service_instances(service_name: str):
                from services.service_registry_service import ServiceRegistryService
                from repositories.service_registry_repository import ServiceRegistryRepository
                
                repo = ServiceRegistryRepository(db_session)
                service = ServiceRegistryService(
                    registry_client, repo, redis_client, health_monitor=health_monitor_service
                )
                return await service.get_service_instances(service_name)
            
            # Monitor all services
            results = await health_monitor_service.monitor_all_services(
                get_service_instances,
                additional_endpoints if additional_endpoints else None,
            )
            
            # Cache a lightweight health snapshot per service for internal consumers.
            # This enables GET /internal/health-status to serve from cache only (<5ms),
            # without DB reads or live probes on request.
            await cache_health_snapshots(
                redis_client,
                results=results,
                health_check_interval=health_check_interval,
            )

            logger.debug(f"Completed health check cycle for {len(results)} services")
            
        except Exception as e:
            logger.error(f"Error in periodic health check: {e}", exc_info=True)
        
        # Wait for next cycle
        await asyncio.sleep(health_check_interval)


@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, kafka_producer, health_monitor_service, health_monitor_task
    
    try:
        # Initialize Redis connection
        redis_client = redis.from_url(app_env.get_redis_url())
        await redis_client.ping()
        logger.info("Connected to Redis")
        # Expose on app.state for routers (avoids circular imports).
        app.state.redis_client = redis_client
        
        # Initialize PostgreSQL connection
        database_url = app_env.get_database_url()
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
            kafka_servers = app_env.kafka_bootstrap_servers
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
            service_name = app_env.service_name or 'config-service'
            service_port = str(app_env.service_port)
            instance_id = app_env.service_instance_id or f"{service_name}-1"
            service_url = f"http://{service_name}:{service_port}"
            health_url = f"{service_url}/health"
            try:
                await registry_client.register_service(service_name, service_url, {"instance_id": instance_id, "health_check_url": health_url, "status": "healthy"})
            except Exception as e:
                logger.warning(f"Failed to register service in ZooKeeper: {e}")
        except Exception as e:
            logger.warning(f"ZooKeeper connection failed: {e}")
        
        # Initialize health monitor service
        try:
            from services.health_monitor_service import HealthMonitorService
            from repositories.service_registry_repository import ServiceRegistryRepository
            
            repo = ServiceRegistryRepository(db_session)
            
            # Configuration from environment variables
            health_check_timeout = float(app_env.health_check_timeout)
            health_check_max_retries = app_env.health_check_max_retries
            health_check_initial_retry_delay = app_env.health_check_initial_retry_delay
            health_check_max_retry_delay = app_env.health_check_max_retry_delay
            health_check_retry_backoff = app_env.health_check_retry_backoff
            
            health_monitor_service = HealthMonitorService(
                repository=repo,
                redis_client=redis_client,
                default_timeout=health_check_timeout,
                max_retries=health_check_max_retries,
                initial_retry_delay=health_check_initial_retry_delay,
                max_retry_delay=health_check_max_retry_delay,
                retry_backoff_multiplier=health_check_retry_backoff,
            )
            logger.info("Health monitor service initialized")
            
            # Start periodic health check task if enabled
            health_check_enabled = app_env.service_health_check_enabled
            if health_check_enabled:
                health_monitor_task = asyncio.create_task(periodic_health_check())
                logger.info("Periodic health check task started")
            else:
                logger.info("Periodic health check disabled")
                
        except Exception as e:
            logger.warning(f"Failed to initialize health monitor service: {e}")
            health_monitor_service = None
        
    except Exception as e:
        logger.error(f"Failed to initialize essential connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, kafka_producer, health_monitor_service, health_monitor_task

    # Cancel health monitor task
    if health_monitor_task:
        health_monitor_task.cancel()
        try:
            await health_monitor_task
        except asyncio.CancelledError:
            pass
        logger.info("Health monitor task cancelled")

    # Close health monitor service
    if health_monitor_service:
        await health_monitor_service.close()
        logger.info("Health monitor service closed")
    
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
            service_name = app_env.service_name or 'config-service'
            instance_id = app_env.service_instance_id or f"{service_name}-1"
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
        "description": "Centralized configuration for microservices"
    }

from routers import (
    config_router,
    service_registry_router,
    health_router,
    internal_health_router,
)
app.include_router(config_router)
app.include_router(service_registry_router)
app.include_router(health_router)
app.include_router(internal_health_router)

@app.get("/api/v1/config/status")
async def config_status():
    """Configuration service status"""
    return {
        "service": "config-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "Environment-specific configurations",
            "Service discovery",
            "Dynamic configuration updates",
            "Configuration audit logging",
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
