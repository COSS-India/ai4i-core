#!/bin/bash

# Quick Docker Manager - Simplified interface for common operations
# This script provides shortcuts for the most common Docker operations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_MANAGER="$SCRIPT_DIR/docker-manager.sh"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Quick Docker Manager - Simplified Docker operations

USAGE:
    $0 <command> [services]

COMMANDS:
    up          Start all services (with smart rebuild)
    down        Stop all services
    restart     Restart all services (with smart rebuild)
    rebuild     Force rebuild and restart all services
    update      Update all services (rebuild if needed)
    status      Show status of all services
    logs        Show logs for all services
    clean       Clean up Docker resources

QUICK COMMANDS:
    dev         Start development environment (microservices only)
    infra       Start infrastructure services only
    nmt         Update NMT service specifically
    gateway     Update API Gateway service specifically
    pipeline    Update Pipeline service specifically
    frontend    Update frontend service specifically
    all         Update all microservices

EXAMPLES:
    # Start everything
    $0 up

    # Start only microservices for development
    $0 dev

    # Update specific service
    $0 nmt
    $0 pipeline

    # Check status
    $0 status

    # Show logs
    $0 logs

For more advanced options, use: ./scripts/docker-manager.sh --help
EOF
}

# Main function
main() {
    case "${1:-}" in
        up)
            print_info "Starting all services..."
            "$DOCKER_MANAGER" start all
            ;;
        down)
            print_info "Stopping all services..."
            "$DOCKER_MANAGER" stop all
            ;;
        restart)
            print_info "Restarting all services..."
            "$DOCKER_MANAGER" restart all
            ;;
        rebuild)
            print_info "Force rebuilding all services..."
            "$DOCKER_MANAGER" rebuild all --force-rebuild
            ;;
        update)
            print_info "Updating all services..."
            "$DOCKER_MANAGER" update all
            ;;
        status)
            "$DOCKER_MANAGER" status all
            ;;
        logs)
            "$DOCKER_MANAGER" logs all
            ;;
        clean)
            "$DOCKER_MANAGER" clean
            ;;
        dev)
            print_info "Starting development environment (microservices only)..."
            "$DOCKER_MANAGER" start microservices
            ;;
        infra)
            print_info "Starting infrastructure services..."
            "$DOCKER_MANAGER" start infrastructure
            ;;
        nmt)
            print_info "Updating NMT service..."
            "$DOCKER_MANAGER" update nmt-service
            ;;
        tts)
            print_info "Updating TTS service..."
            "$DOCKER_MANAGER" update tts-service
            ;;
        asr)
            print_info "Updating ASR service..."
            "$DOCKER_MANAGER" update asr-service
            ;;
        config)
            print_info "Updating Config service..."
            "$DOCKER_MANAGER" update config-service
            ;;
        metrics)
            print_info "Updating Metrics service..."
            "$DOCKER_MANAGER" update metrics-service
            ;;
        telemetry)
            print_info "Updating Telemetry service..."
            "$DOCKER_MANAGER" update telemetry-service
            ;;
        alerting)
            print_info "Updating Alerting service..."
            "$DOCKER_MANAGER" update alerting-service
            ;;
        dashboard)
            print_info "Updating Dashboard service..."
            "$DOCKER_MANAGER" update dashboard-service
            ;;
        gateway)
            print_info "Updating API Gateway service..."
            "$DOCKER_MANAGER" update api-gateway-service
            ;;
        pipeline)
            print_info "Updating Pipeline service..."
            "$DOCKER_MANAGER" update pipeline-service
            ;;
        frontend)
            print_info "Updating frontend service..."
            "$DOCKER_MANAGER" update simple-ui-frontend
            ;;
        all)
            print_info "Updating all microservices..."
            "$DOCKER_MANAGER" update microservices
            ;;
        -h|--help|help)
            show_usage
            ;;
        *)
            if [[ -z "${1:-}" ]]; then
                print_info "No command specified. Showing usage:"
                echo
            else
                print_info "Unknown command: $1"
                echo
            fi
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
