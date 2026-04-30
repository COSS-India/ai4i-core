#!/bin/bash

# Check health status of all services
# This script checks the health of all services and displays results in a formatted table

set -e

# Change to project directory
cd "$(dirname "$0")/.."

echo "Checking health status of all services..."
echo ""

# Function to check service health
check_service_health() {
    local service_name=$1
    local health_status="unhealthy"
    local response_time="N/A"
    local start_time=$(date +%s%3N)
    
    case $service_name in
        api-gateway-service)
            if curl -f -s http://localhost:8080/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        auth-service)
            if curl -f -s http://localhost:8081/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        config-service)
            if curl -f -s http://localhost:8082/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        metrics-service)
            if curl -f -s http://localhost:8083/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        telemetry-service)
            if curl -f -s http://localhost:8084/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        alerting-service)
            if curl -f -s http://localhost:8085/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        dashboard-service)
            if curl -f -s http://localhost:8086/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        asr-service)
            if curl -f -s http://localhost:8087/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        tts-service)
            if curl -f -s http://localhost:8088/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        nmt-service)
            if curl -f -s http://localhost:8089/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        pipeline-service)
            if curl -f -s http://localhost:8092/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        simple-ui-frontend)
            if curl -f -s http://localhost:3000/api/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        postgres)
            if docker compose exec postgres pg_isready -U "${POSTGRES_USER:-dhruva_user}" > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        redis)
            if docker compose exec redis redis-cli -a "${REDIS_PASSWORD:-redis_secure_password_2024}" ping > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        influxdb)
            if curl -f -s http://localhost:8086/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        elasticsearch)
            if curl -f -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" http://localhost:9200/_cluster/health > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        kafka)
            if kafka-broker-api-versions --bootstrap-server localhost:9092 > /dev/null 2>&1; then
                health_status="healthy"
            fi
            ;;
        zookeeper)
            if nc -z localhost 2181 2>/dev/null; then
                health_status="healthy"
            fi
            ;;
    esac
    
    local end_time=$(date +%s%3N)
    response_time=$((end_time - start_time))
    
    echo "$service_name|$health_status|${response_time}ms"
}

# Get all services from docker-compose
SERVICES=($(docker compose config --services))

# Check if any services are running
if [ ${#SERVICES[@]} -eq 0 ]; then
    echo "No services found. Make sure Docker Compose is properly configured."
    exit 1
fi

# Print header
printf "%-25s %-10s %-12s\n" "SERVICE" "STATUS" "RESPONSE TIME"
echo "--------------------------------------------------------"

# Check health of each service
overall_healthy=true
for service in "${SERVICES[@]}"; do
    # Check if container is running
    if ! docker compose ps -q $service | xargs docker ps -q --filter id= > /dev/null 2>&1; then
        printf "%-25s %-10s %-12s\n" "$service" "stopped" "N/A"
        overall_healthy=false
        continue
    fi
    
    # Check service health
    health_result=$(check_service_health $service)
    service_name=$(echo $health_result | cut -d'|' -f1)
    health_status=$(echo $health_result | cut -d'|' -f2)
    response_time=$(echo $health_result | cut -d'|' -f3)
    
    # Color code the status
    if [ "$health_status" = "healthy" ]; then
        printf "%-25s \033[32m%-10s\033[0m %-12s\n" "$service_name" "$health_status" "$response_time"
    else
        printf "%-25s \033[31m%-10s\033[0m %-12s\n" "$service_name" "$health_status" "$response_time"
        overall_healthy=false
    fi
done

echo "--------------------------------------------------------"

# Print summary
if [ "$overall_healthy" = true ]; then
    echo -e "\033[32mAll services are healthy!\033[0m"
    exit 0
else
    echo -e "\033[31mSome services are unhealthy. Check the logs for more details.\033[0m"
    echo ""
    echo "To view logs: ./scripts/logs.sh"
    echo "To restart a service: ./scripts/restart-service.sh <service-name>"
    exit 1
fi
