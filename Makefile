# Dhruva Microservices Platform Makefile
# Convenient commands for managing the microservices platform

.PHONY: help start stop restart logs health init clean build rebuild shell test

# Default target
help:
	@echo "Dhruva Microservices Platform - Available Commands:"
	@echo ""
	@echo "  start     - Start all services"
	@echo "  stop      - Stop all services"
	@echo "  restart   - Stop then start all services"
	@echo "  logs      - View logs for all services"
	@echo "  health    - Check health status of all services"
	@echo "  init      - Initialize infrastructure components"
	@echo "  clean     - Stop all services and remove volumes"
	@echo "  build     - Build all Docker images"
	@echo "  rebuild   - Clean build all Docker images"
	@echo "  test      - Run tests (when implemented)"
	@echo ""
	@echo "Service-specific commands:"
	@echo "  shell-<service> - Open shell in service container"
	@echo "  logs-<service>  - View logs for specific service"
	@echo ""
	@echo "Available services:"
	@echo "  api-gateway-service, auth-service, config-service"
	@echo "  metrics-service, telemetry-service, alerting-service"
	@echo "  dashboard-service, asr-service, tts-service, nmt-service"
	@echo "  pipeline-service, postgres, redis, influxdb"
	@echo "  elasticsearch, kafka, zookeeper, vault"

# Start all services
start:
	@echo "Starting all services..."
	@./scripts/start-all.sh

# Stop all services
stop:
	@echo "Stopping all services..."
	@./scripts/stop-all.sh

# Restart all services
restart: stop start

# View logs for all services
logs:
	@./scripts/logs.sh

# Check health status
health:
	@./scripts/health-check-all.sh

# Initialize infrastructure
init:
	@echo "Initializing infrastructure..."
	@./scripts/init-infrastructure.sh

# Clean stop and remove volumes
clean:
	@echo "Cleaning up (stopping services and removing volumes)..."
	@./scripts/stop-all.sh --volumes

# Build all Docker images
build:
	@echo "Building all Docker images..."
	@docker-compose build

# Rebuild all Docker images (clean build)
rebuild: clean
	@echo "Rebuilding all Docker images..."
	@docker-compose build --no-cache

# Run tests (placeholder for future implementation)
test:
	@echo "Running tests..."
	@echo "Test implementation coming soon..."

# Service-specific shell commands
shell-api-gateway:
	@docker-compose exec api-gateway-service /bin/bash

shell-auth:
	@docker-compose exec auth-service /bin/bash

shell-config:
	@docker-compose exec config-service /bin/bash

shell-metrics:
	@docker-compose exec metrics-service /bin/bash

shell-telemetry:
	@docker-compose exec telemetry-service /bin/bash

shell-alerting:
	@docker-compose exec alerting-service /bin/bash

shell-dashboard:
	@docker-compose exec dashboard-service /bin/bash

shell-asr:
	@docker-compose exec asr-service /bin/bash

shell-tts:
	@docker-compose exec tts-service /bin/bash

shell-nmt:
	@docker-compose exec nmt-service /bin/bash

shell-pipeline:
	@docker-compose exec pipeline-service /bin/bash

shell-postgres:
	@docker-compose exec postgres /bin/bash

shell-redis:
	@docker-compose exec redis /bin/bash

shell-influxdb:
	@docker-compose exec influxdb /bin/bash

shell-elasticsearch:
	@docker-compose exec elasticsearch /bin/bash

shell-kafka:
	@docker-compose exec kafka /bin/bash

shell-zookeeper:
	@docker-compose exec zookeeper /bin/bash

shell-vault:
	@docker-compose exec vault /bin/sh

# Service-specific log commands
logs-api-gateway:
	@./scripts/logs.sh api-gateway-service

logs-auth:
	@./scripts/logs.sh auth-service

logs-config:
	@./scripts/logs.sh config-service

logs-metrics:
	@./scripts/logs.sh metrics-service

logs-telemetry:
	@./scripts/logs.sh telemetry-service

logs-alerting:
	@./scripts/logs.sh alerting-service

logs-dashboard:
	@./scripts/logs.sh dashboard-service

logs-asr:
	@./scripts/logs.sh asr-service

logs-tts:
	@./scripts/logs.sh tts-service

logs-nmt:
	@./scripts/logs.sh nmt-service

logs-pipeline:
	@./scripts/logs.sh pipeline-service

logs-postgres:
	@./scripts/logs.sh postgres

logs-redis:
	@./scripts/logs.sh redis

logs-influxdb:
	@./scripts/logs.sh influxdb

logs-elasticsearch:
	@./scripts/logs.sh elasticsearch

logs-kafka:
	@./scripts/logs.sh kafka

logs-zookeeper:
	@./scripts/logs.sh zookeeper

logs-vault:
	@./scripts/logs.sh vault

# Service restart commands
restart-api-gateway:
	@./scripts/restart-service.sh api-gateway-service

restart-auth:
	@./scripts/restart-service.sh auth-service

restart-config:
	@./scripts/restart-service.sh config-service

restart-metrics:
	@./scripts/restart-service.sh metrics-service

restart-telemetry:
	@./scripts/restart-service.sh telemetry-service

restart-alerting:
	@./scripts/restart-service.sh alerting-service

restart-dashboard:
	@./scripts/restart-service.sh dashboard-service

restart-asr:
	@./scripts/restart-service.sh asr-service

restart-tts:
	@./scripts/restart-service.sh tts-service

restart-nmt:
	@./scripts/restart-service.sh nmt-service

restart-pipeline:
	@./scripts/restart-service.sh pipeline-service

restart-postgres:
	@./scripts/restart-service.sh postgres

restart-redis:
	@./scripts/restart-service.sh redis

restart-influxdb:
	@./scripts/restart-service.sh influxdb

restart-elasticsearch:
	@./scripts/restart-service.sh elasticsearch

restart-kafka:
	@./scripts/restart-service.sh kafka

restart-zookeeper:
	@./scripts/restart-service.sh zookeeper

restart-vault:
	@./scripts/restart-service.sh vault

# Development commands
dev-start:
	@echo "Starting in development mode with hot-reloading..."
	@docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

dev-stop:
	@echo "Stopping development environment..."
	@docker-compose -f docker-compose.yml -f docker-compose.override.yml down

dev-restart: dev-stop dev-start

# Database commands
db-reset:
	@echo "Resetting databases (WARNING: This will delete all data)..."
	@read -p "Are you sure? (y/N): " confirm && [ "$$confirm" = "y" ] || exit 1
	@./scripts/stop-all.sh --volumes
	@./scripts/start-all.sh

# Status commands
status:
	@echo "Service Status:"
	@docker-compose ps

ps:
	@docker-compose ps

# Cleanup commands
cleanup-images:
	@echo "Removing unused Docker images..."
	@docker image prune -f

cleanup-volumes:
	@echo "Removing unused Docker volumes..."
	@docker volume prune -f

cleanup-all: cleanup-images cleanup-volumes
	@echo "Cleaning up all unused Docker resources..."
	@docker system prune -f

# Show service URLs
urls:
	@echo "Service URLs:"
	@echo "  API Gateway:     http://localhost:8080"
	@echo "  Auth Service:    http://localhost:8081"
	@echo "  Config Service:  http://localhost:8082"
	@echo "  Metrics Service: http://localhost:8083"
	@echo "  Telemetry Service: http://localhost:8084"
	@echo "  Alerting Service: http://localhost:8085"
	@echo "  Dashboard Service: http://localhost:8086"
	@echo "  ASR Service: http://localhost:8087"
	@echo "  TTS Service: http://localhost:8088"
	@echo "  NMT Service: http://localhost:8091"
	@echo "  Pipeline Service: http://localhost:8092"
	@echo "  Streamlit Dashboard: http://localhost:8501"
	@echo ""
	@echo "Infrastructure:"
	@echo "  PostgreSQL:      localhost:5432"
	@echo "  Redis:           localhost:6379"
	@echo "  InfluxDB:        http://localhost:8086"
	@echo "  Elasticsearch:   http://localhost:9200"
	@echo "  Kafka:           localhost:9092"
	@echo "  Vault:           http://localhost:8200"
