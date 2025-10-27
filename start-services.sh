#!/bin/bash

# Start AI4V Microservices
echo "Starting AI4V Microservices..."

# Set project name
export COMPOSE_PROJECT_NAME=ai4v-microservices

# Change to the project directory
#cd /home/appala/Projects/AI4V-Core/Ai4V-C
# cd /home/supriya/AI4X/AI4v-Core/aiv4-core/
cd /home/geojoseph/Desktop/coss/aiv4-core/

# Stop any existing containers
echo "Stopping existing containers..."
docker compose down --remove-orphans 2>/dev/null || true

# Start infrastructure services first
echo "Starting infrastructure services..."
docker compose up -d postgres redis influxdb elasticsearch zookeeper kafka

# Wait for infrastructure to be ready
echo "Waiting for infrastructure services to be ready..."
sleep 30

# Start microservices
echo "Starting microservices..."
docker compose up -d api-gateway-service auth-service config-service metrics-service telemetry-service alerting-service dashboard-service asr-service tts-service nmt-service pipeline-service

# Wait for microservices to be ready
echo "Waiting for microservices to be ready..."
sleep 30

# Start frontend
echo "Starting frontend..."
docker compose up -d simple-ui-frontend

echo "All services started!"
echo "Services are available at:"
echo "- API Gateway: http://localhost:8080"
echo "- Frontend: http://localhost:3000"
echo "- PostgreSQL: localhost:5433"
echo "- Redis: localhost:6380"
echo "- InfluxDB: http://localhost:8087"
echo "- Elasticsearch: http://localhost:9201"
echo "- Kafka: localhost:9092"

