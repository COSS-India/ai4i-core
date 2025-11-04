"""
Alerting Service - Proactive issue detection and notification
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from sklearn.ensemble import IsolationForest
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Alerting Service",
    version="1.0.0",
    description="Proactive issue detection and notification for microservices"
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
kafka_consumer = None
anomaly_detector = None

class AnomalyDetector:
    def __init__(self):
        self.model = IsolationForest(contamination=0.1)
        self.training_data = []
        self.is_trained = False
    
    def add_training_data(self, data_point: float):
        """Add data point for training"""
        self.training_data.append(data_point)
        if len(self.training_data) > 1000:
            self.training_data = self.training_data[-1000:]  # Keep last 1000 points
    
    def train_model(self):
        """Train anomaly detection model"""
        if len(self.training_data) < 100:
            return False
        
        X = np.array(self.training_data).reshape(-1, 1)
        self.model.fit(X)
        self.is_trained = True
        return True
    
    def detect_anomaly(self, data_point: float) -> bool:
        """Detect if data point is anomalous"""
        if not self.is_trained:
            return False
        
        X = np.array([[data_point]])
        prediction = self.model.predict(X)
        return prediction[0] == -1  # -1 indicates anomaly

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, db_engine, db_session, kafka_producer, kafka_consumer, anomaly_detector
    
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
            'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/alerting_db'
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
        logger.info("Connected to Kafka producer")
        
        # Initialize Kafka consumer
        kafka_consumer = AIOKafkaConsumer(
            'metrics',
            bootstrap_servers=kafka_servers,
            value_deserializer=lambda m: m.decode('utf-8')
        )
        await kafka_consumer.start()
        logger.info("Connected to Kafka consumer")
        
        # Initialize anomaly detector
        anomaly_detector = AnomalyDetector()
        logger.info("Anomaly detector initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize connections: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up connections on shutdown"""
    global redis_client, db_engine, kafka_producer, kafka_consumer
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    
    if db_engine:
        await db_engine.dispose()
        logger.info("PostgreSQL connection closed")
    
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
        "service": "Alerting Service",
        "version": "1.0.0",
        "status": "running",
        "description": "Proactive issue detection and notification for microservices"
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
        if kafka_producer and kafka_consumer:
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
            "service": "alerting-service",
            "redis": redis_status,
            "postgres": postgres_status,
            "kafka": kafka_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/api/v1/alerting/status")
async def alerting_status():
    """Alerting service status"""
    return {
        "service": "alerting-service",
        "version": "v1",
        "status": "operational",
        "features": [
            "Anomaly detection",
            "Threshold-based alerting",
            "Alert routing and escalation",
            "Integration with notification systems"
        ]
    }

@app.post("/api/v1/alerting/rules")
async def create_alert_rule():
    """Create new alert rule"""
    return {"message": "Alert rule creation - to be implemented"}

@app.post("/api/v1/alerting/metrics")
async def evaluate_metric():
    """Evaluate metric against alert rules"""
    return {"message": "Metric evaluation - to be implemented"}

@app.get("/api/v1/alerting/alerts")
async def get_active_alerts():
    """Get all active alerts"""
    return {"message": "Active alerts retrieval - to be implemented"}

@app.post("/api/v1/alerting/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an alert"""
    return {"message": f"Alert {alert_id} acknowledgment - to be implemented"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085)
