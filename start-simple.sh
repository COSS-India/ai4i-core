#!/bin/bash

# Simple script to start AI4V Microservices without health checks
echo "Starting AI4V Microservices (Simple Mode)..."

# Set project name
export COMPOSE_PROJECT_NAME=ai4v-microservices

# Change to the project directory
cd /home/appala/Projects/AI4V-Core/Ai4V-C

# Stop any existing containers
echo "Stopping existing containers..."
docker-compose down --remove-orphans 2>/dev/null || true

# Start infrastructure services without health checks
echo "Starting infrastructure services..."
docker run -d --name ai4v-postgres --network ai4v-microservices_microservices-network -p 5434:5432 -e POSTGRES_USER=dhruva_user -e POSTGRES_PASSWORD=dhruva_secure_password_2024 -e POSTGRES_DB=dhruva_platform -v ai4v-microservices_postgres-data:/var/lib/postgresql/data postgres:15-alpine

docker run -d --name ai4v-redis --network ai4v-microservices_microservices-network -p 6381:6379 -e REDIS_PASSWORD=redis_secure_password_2024 redis:7-alpine

docker run -d --name ai4v-influxdb --network ai4v-microservices_microservices-network -p 8089:8086 -e DOCKER_INFLUXDB_INIT_MODE=setup -e DOCKER_INFLUXDB_INIT_USERNAME=admin -e DOCKER_INFLUXDB_INIT_PASSWORD=influx_secure_password_2024 -e DOCKER_INFLUXDB_INIT_ORG=dhruva-org -e DOCKER_INFLUXDB_INIT_BUCKET=metrics -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=dhruva-influx-token-2024 influxdb:2.7-alpine

docker run -d --name ai4v-elasticsearch --network ai4v-microservices_microservices-network -p 9203:9200 -e discovery.type=single-node -e xpack.security.enabled=false -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" docker.elastic.co/elasticsearch/elasticsearch:8.10.0

docker run -d --name ai4v-zookeeper --network ai4v-microservices_microservices-network -p 2182:2181 -e ZOOKEEPER_CLIENT_PORT=2181 -e ZOOKEEPER_TICK_TIME=2000 confluentinc/cp-zookeeper:7.4.0

# Wait for infrastructure to be ready
echo "Waiting for infrastructure services to be ready..."
sleep 30

# Start microservices
echo "Starting microservices..."
COMPOSE_PROJECT_NAME=ai4v-microservices docker-compose up -d api-gateway-service auth-service config-service metrics-service telemetry-service alerting-service dashboard-service asr-service tts-service nmt-service pipeline-service

# Wait for microservices to be ready
echo "Waiting for microservices to be ready..."
sleep 30

# Start frontend
echo "Starting frontend..."
COMPOSE_PROJECT_NAME=ai4v-microservices docker-compose up -d simple-ui-frontend

echo "All services started!"
echo "Services are available at:"
echo "- API Gateway: http://localhost:8080"
echo "- Frontend: http://localhost:3000"
echo "- PostgreSQL: localhost:5434"
echo "- Redis: localhost:6381"
echo "- InfluxDB: http://localhost:8089"
echo "- Elasticsearch: http://localhost:9203"
echo "- Kafka: localhost:9093"

