#!/bin/bash

# Start all services in the correct order
# This script starts infrastructure services first, then microservices

set -e

echo "Starting Dhruva Microservices Platform..."

# Change to project directory
cd "$(dirname "$0")/.."

# Start infrastructure services first
echo "Starting infrastructure services..."
docker-compose up -d postgres redis influxdb elasticsearch zookeeper kafka

# Wait for infrastructure services to be healthy
echo "Waiting for infrastructure services to be healthy..."

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until docker-compose exec postgres pg_isready -U "${POSTGRES_USER:-dhruva_user}" > /dev/null 2>&1; do
    echo "PostgreSQL is not ready yet, waiting..."
    sleep 5
done
echo "PostgreSQL is ready"

# Wait for Redis
echo "Waiting for Redis..."
until docker-compose exec redis redis-cli -a "${REDIS_PASSWORD:-redis_secure_password_2024}" ping > /dev/null 2>&1; do
    echo "Redis is not ready yet, waiting..."
    sleep 5
done
echo "Redis is ready"

# Wait for InfluxDB
echo "Waiting for InfluxDB..."
until curl -f http://localhost:8086/health > /dev/null 2>&1; do
    echo "InfluxDB is not ready yet, waiting..."
    sleep 5
done
echo "InfluxDB is ready"

# Wait for Elasticsearch
echo "Waiting for Elasticsearch..."
until curl -f -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" http://localhost:9200/_cluster/health > /dev/null 2>&1; do
    echo "Elasticsearch is not ready yet, waiting..."
    sleep 5
done
echo "Elasticsearch is ready"

# Wait for Kafka
echo "Waiting for Kafka..."
until kafka-broker-api-versions --bootstrap-server localhost:9092 > /dev/null 2>&1; do
    echo "Kafka is not ready yet, waiting..."
    sleep 5
done
echo "Kafka is ready"

# Run initialization scripts
echo "Running infrastructure initialization scripts..."
./scripts/init-infrastructure.sh

# Start all microservices
echo "Starting microservices..."
docker-compose up -d api-gateway-service auth-service config-service metrics-service telemetry-service alerting-service dashboard-service

# Wait for microservices to be healthy
echo "Waiting for microservices to be healthy..."

# Wait for API Gateway
echo "Waiting for API Gateway..."
until curl -f http://localhost:8080/health > /dev/null 2>&1; do
    echo "API Gateway is not ready yet, waiting..."
    sleep 5
done
echo "API Gateway is ready"

# Wait for Auth Service
echo "Waiting for Auth Service..."
until curl -f http://localhost:8081/health > /dev/null 2>&1; do
    echo "Auth Service is not ready yet, waiting..."
    sleep 5
done
echo "Auth Service is ready"

# Wait for Config Service
echo "Waiting for Config Service..."
until curl -f http://localhost:8082/health > /dev/null 2>&1; do
    echo "Config Service is not ready yet, waiting..."
    sleep 5
done
echo "Config Service is ready"

# Wait for Metrics Service
echo "Waiting for Metrics Service..."
until curl -f http://localhost:8083/health > /dev/null 2>&1; do
    echo "Metrics Service is not ready yet, waiting..."
    sleep 5
done
echo "Metrics Service is ready"

# Wait for Telemetry Service
echo "Waiting for Telemetry Service..."
until curl -f http://localhost:8084/health > /dev/null 2>&1; do
    echo "Telemetry Service is not ready yet, waiting..."
    sleep 5
done
echo "Telemetry Service is ready"

# Wait for Alerting Service
echo "Waiting for Alerting Service..."
until curl -f http://localhost:8085/health > /dev/null 2>&1; do
    echo "Alerting Service is not ready yet, waiting..."
    sleep 5
done
echo "Alerting Service is ready"

# Wait for Dashboard Service
echo "Waiting for Dashboard Service..."
until curl -f http://localhost:8086/health > /dev/null 2>&1; do
    echo "Dashboard Service is not ready yet, waiting..."
    sleep 5
done
echo "Dashboard Service is ready"

echo "All services are up and running!"
echo ""
echo "Service URLs:"
echo "  API Gateway:     http://localhost:8080"
echo "  Auth Service:    http://localhost:8081"
echo "  Config Service:  http://localhost:8082"
echo "  Metrics Service: http://localhost:8083"
echo "  Telemetry Service: http://localhost:8084"
echo "  Alerting Service: http://localhost:8085"
echo "  Dashboard Service: http://localhost:8086"
echo "  Streamlit Dashboard: http://localhost:8501"
echo ""
echo "Infrastructure:"
echo "  PostgreSQL:      localhost:5432"
echo "  Redis:           localhost:6379"
echo "  InfluxDB:        http://localhost:8086"
echo "  Elasticsearch:   http://localhost:9200"
echo "  Kafka:           localhost:9092"
echo ""
echo "To view logs: ./scripts/logs.sh"
echo "To check health: ./scripts/health-check-all.sh"
echo "To stop all services: ./scripts/stop-all.sh"
