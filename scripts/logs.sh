#!/bin/bash

# View logs for services
# This script shows logs for specific services or all services

set -e

# Change to project directory
cd "$(dirname "$0")/.."

# Parse command line arguments
SERVICE_NAME=""
FOLLOW_FLAG=""
TAIL_LINES=100
TIMESTAMPS_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--follow)
            FOLLOW_FLAG="-f"
            shift
            ;;
        -t|--timestamps)
            TIMESTAMPS_FLAG="-t"
            shift
            ;;
        --tail)
            TAIL_LINES="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [service-name] [options]"
            echo ""
            echo "Arguments:"
            echo "  service-name    Name of the service to view logs for (optional)"
            echo ""
            echo "Options:"
            echo "  -f, --follow    Follow log output"
            echo "  -t, --timestamps Show timestamps"
            echo "  --tail N        Number of lines to show (default: 100)"
            echo "  -h, --help      Show this help message"
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
            echo "Examples:"
            echo "  $0                    # Show logs for all services"
            echo "  $0 api-gateway-service # Show logs for API Gateway"
            echo "  $0 -f auth-service    # Follow logs for Auth Service"
            echo "  $0 --tail 50 postgres # Show last 50 lines for PostgreSQL"
            exit 0
            ;;
        *)
            if [ -z "$SERVICE_NAME" ]; then
                SERVICE_NAME="$1"
            else
                echo "Error: Multiple service names provided"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate service name if provided
if [ -n "$SERVICE_NAME" ]; then
    VALID_SERVICES=("api-gateway-service" "auth-service" "config-service" "metrics-service" "telemetry-service" "alerting-service" "dashboard-service" "postgres" "redis" "influxdb" "elasticsearch" "kafka" "zookeeper")
    
    if [[ ! " ${VALID_SERVICES[@]} " =~ " ${SERVICE_NAME} " ]]; then
        echo "Error: Invalid service name '$SERVICE_NAME'"
        echo "Available services: ${VALID_SERVICES[*]}"
        exit 1
    fi
fi

# Show logs
if [ -n "$SERVICE_NAME" ]; then
    echo "Showing logs for $SERVICE_NAME..."
    docker-compose logs $FOLLOW_FLAG $TIMESTAMPS_FLAG --tail=$TAIL_LINES $SERVICE_NAME
else
    echo "Showing logs for all services..."
    docker-compose logs $FOLLOW_FLAG $TIMESTAMPS_FLAG --tail=$TAIL_LINES
fi
