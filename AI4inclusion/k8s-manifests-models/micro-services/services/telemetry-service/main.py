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
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

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
kafka_producer = None
kafka_consumer = None

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, es_client, kafka_producer, kafka_consumer
    
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
        
        # Initialize Kafka producer
        kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
        kafka_producer = AIOKafkaProducer(
            bootstrap_servers=kafka_servers,
            value_serializer=lambda v: str(v).encode('utf-8')
        )
        await kafka_producer.start()
        logger.info("Connected to Kafka producer")
        
        # Initialize Kafka consumer
        kafka_consumer = AIOKafkaConsumer(
            'logs',
            'traces',
            bootstrap_servers=kafka_servers,
            value_deserializer=lambda m: m.decode('utf-8')
        )
        await kafka_consumer.start()
        logger.info("Connected to Kafka consumer")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, es_client, kafka_producer, kafka_consumer
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
    if es_client:
        await es_client.close()
        logger.info("Elasticsearch connection closed")
    
    if kafka_producer:
        await kafka_producer.stop()
        logger.info("Kafka producer closed")
    
    if kafka_consumer:
        await kafka_consumer.stop()
        logger.info("Kafka consumer closed")

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
            async with db_engine.begin() as conn:
                await conn.execute("SELECT 1")
            postgres_status = "healthy"
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
        
        # Check Kafka connectivity
        if kafka_producer and kafka_consumer:
            kafka_status = "healthy"
        else:
            kafka_status = "unhealthy"
        
        overall_status = "healthy" if all([
            redis_status == "healthy", 
            postgres_status == "healthy",
            elasticsearch_status == "healthy",
            kafka_status == "healthy"
        ]) else "unhealthy"
        
        return {
            "status": overall_status,
            "service": "telemetry-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "elasticsearch": elasticsearch_status,
            "kafka": kafka_status,
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)
