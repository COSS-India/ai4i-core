"""
Metrics Collection Service - Collect and aggregate system metrics
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
from influxdb_client import InfluxDBClient
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Metrics Collection Service",
    version="1.0.0",
    description="Collect and aggregate system metrics for microservices"
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
influx_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, influx_client
    
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
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/metrics_db'
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
        
        # Initialize InfluxDB client
        influx_url = os.getenv('INFLUXDB_URL', 'http://influxdb:8086')
        influx_token = os.getenv('INFLUXDB_TOKEN', 'dhruva-influx-token-2024')
        influx_org = os.getenv('INFLUXDB_ORG', 'dhruva-org')
        
        influx_client = InfluxDBClient(
            url=influx_url,
            token=influx_token,
            org=influx_org
        )
        logger.info("Connected to InfluxDB")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, influx_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if influx_client:
        influx_client.close()
        logger.info("InfluxDB connection closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Metrics Collection Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Collect and aggregate system metrics for microservices"
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
        
        # Check InfluxDB connectivity
        if influx_client:
            try:
                influx_client.ping()
                influx_status = "healthy"
            except:
                influx_status = "unhealthy"
        else:
            influx_status = "unhealthy"
        
        overall_status = "healthy" if all([
            redis_status == "healthy", 
            postgres_status == "healthy",
            influx_status == "healthy"
        ]) else "unhealthy"
        
        return {
            "status": overall_status,
            "service": "metrics-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "influxdb": influx_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/metrics/status")
async def metrics_status():
    """Metrics service status"""
    return {
        "service": "metrics-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "API usage metrics",
            "System performance metrics",
            "Custom business metrics",
            "Real-time data streaming"
        ]
    }

@app.get("/api/v1/metrics/system")
async def get_system_metrics():
    """Get current system metrics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_usage": cpu_percent,
            "memory_usage": memory.percent,
            "memory_available": memory.available,
            "disk_usage": disk.percent,
            "disk_free": disk.free
        }
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve system metrics")

@app.post("/api/v1/metrics")
async def collect_metric():
    """Collect custom metric"""
    return {"message": "Metric collection - to be implemented"}

@app.get("/api/v1/metrics/aggregated")
async def get_aggregated_metrics():
    """Get aggregated metrics"""
    return {"message": "Aggregated metrics retrieval - to be implemented"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)
