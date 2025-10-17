#!/bin/bash

# Restart a specific service
# This script restarts a single service with optional rebuild

set -e

# Check if service name is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <service-name> [--build]"
    echo ""
    echo "Available services:"
    echo "  api-gateway-service"
    echo "  auth-service"
    echo "  config-service"
    echo "  metrics-service"
    echo "  telemetry-service"
    echo "  alerting-service"
    echo "  dashboard-service"
    echo "  postgres"
    echo "  redis"
    echo "  influxdb"
    echo "  elasticsearch"
    echo "  kafka"
    echo "  zookeeper"
    echo ""
    echo "Options:"
    echo "  --build    Rebuild the service before restarting"
    exit 1
fi

SERVICE_NAME=$1
BUILD_FLAG=""

# Check for build flag
if [ "$2" = "--build" ]; then
    BUILD_FLAG="--build"
fi

# Change to project directory
cd "$(dirname "$0")/.."

# Validate service name
VALID_SERVICES=("api-gateway-service" "auth-service" "config-service" "metrics-service" "telemetry-service" "alerting-service" "dashboard-service" "postgres" "redis" "influxdb" "elasticsearch" "kafka" "zookeeper")

if [[ ! " ${VALID_SERVICES[@]} " =~ " ${SERVICE_NAME} " ]]; then
    echo "Error: Invalid service name '$SERVICE_NAME'"
    echo "Available services: ${VALID_SERVICES[*]}"
    exit 1
fi

echo "Restarting service: $SERVICE_NAME"

# Restart the service
if [ "$BUILD_FLAG" = "--build" ]; then
    echo "Rebuilding and restarting $SERVICE_NAME..."
    docker-compose up -d $BUILD_FLAG $SERVICE_NAME
else
    echo "Restarting $SERVICE_NAME..."
    docker-compose restart $SERVICE_NAME
fi

# Wait for service to be healthy
echo "Waiting for $SERVICE_NAME to be healthy..."

# Determine health check based on service type
case $SERVICE_NAME in
    api-gateway-service)
        HEALTH_URL="http://localhost:8080/health"
        ;;
    auth-service)
        HEALTH_URL="http://localhost:8081/health"
        ;;
    config-service)
        HEALTH_URL="http://localhost:8082/health"
        ;;
    metrics-service)
        HEALTH_URL="http://localhost:8083/health"
        ;;
    telemetry-service)
        HEALTH_URL="http://localhost:8084/health"
        ;;
    alerting-service)
        HEALTH_URL="http://localhost:8085/health"
        ;;
    dashboard-service)
        HEALTH_URL="http://localhost:8086/health"
        ;;
    postgres)
        # Use pg_isready for PostgreSQL
        until docker-compose exec postgres pg_isready -U "${POSTGRES_USER:-dhruva_user}" > /dev/null 2>&1; do
            echo "PostgreSQL is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
    redis)
        # Use redis-cli ping for Redis
        until docker-compose exec redis redis-cli -a "${REDIS_PASSWORD:-redis_secure_password_2024}" ping > /dev/null 2>&1; do
            echo "Redis is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
    influxdb)
        # Use curl for InfluxDB
        until curl -f http://localhost:8086/health > /dev/null 2>&1; do
            echo "InfluxDB is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
    elasticsearch)
        # Use curl for Elasticsearch
        until curl -f -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" http://localhost:9200/_cluster/health > /dev/null 2>&1; do
            echo "Elasticsearch is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
    kafka)
        # Use kafka-broker-api-versions for Kafka
        until kafka-broker-api-versions --bootstrap-server localhost:9092 > /dev/null 2>&1; do
            echo "Kafka is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
    zookeeper)
        # Use nc for Zookeeper
        until nc -z localhost 2181; do
            echo "Zookeeper is not ready yet, waiting..."
            sleep 2
        done
        echo "$SERVICE_NAME is healthy"
        exit 0
        ;;
esac

# Wait for HTTP health check
until curl -f $HEALTH_URL > /dev/null 2>&1; do
    echo "$SERVICE_NAME is not ready yet, waiting..."
    sleep 2
done

echo "$SERVICE_NAME is healthy and running!"

# Show service logs
echo "Showing recent logs for $SERVICE_NAME:"
docker-compose logs --tail=10 $SERVICE_NAME
