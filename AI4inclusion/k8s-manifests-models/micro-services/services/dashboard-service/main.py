"""
Dashboard Service - Visualization and reporting
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
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Dashboard Service",
    version="1.0.0",
    description="Visualization and reporting for microservices"
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
http_client = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, influx_client, http_client
    
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
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/dashboard_db'
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
        
        # Initialize HTTP client
        http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("HTTP client initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, influx_client, http_client
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if influx_client:
        influx_client.close()
        logger.info("InfluxDB connection closed")
    
    if http_client:
        await http_client.aclose()
        logger.info("HTTP client closed")

@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "Dashboard Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Visualization and reporting for microservices",
        "streamlit_url": f"http://localhost:{os.getenv('STREAMLIT_PORT', '8501')}"
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
            "service": "dashboard-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "influxdb": influx_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/dashboard/status")
async def dashboard_status():
    """Dashboard service status"""
    return {
        "service": "dashboard-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "Real-time dashboards",
            "Executive reporting",
            "Custom analytics views",
            "Data export capabilities"
        ]
    }

@app.get("/api/v1/dashboard/metrics/{metric_name}")
async def get_metric_data(metric_name: str, time_range: str = "1h"):
    """API endpoint for metric data"""
    return {
        "metric_name": metric_name,
        "time_range": time_range,
        "message": "Metric data retrieval - to be implemented"
    }

@app.get("/api/v1/dashboard/health")
async def get_system_health():
    """API endpoint for system health"""
    return {
        "message": "System health data - to be implemented"
    }

@app.get("/api/v1/dashboard/export")
async def export_data():
    """Export dashboard data"""
    return {"message": "Data export - to be implemented"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8086)
