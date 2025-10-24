#!/bin/bash

# Docker Manager Script
# Comprehensive script for managing Docker containers in the microservices architecture
# Supports updates, rebuilds, restarts, and environment management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Default values
ACTION=""
SERVICES=""
FORCE_REBUILD=false
SKIP_ENV_CHECK=false
PARALLEL=false
VERBOSE=false

# All available services
ALL_SERVICES=(
    "api-gateway-service"
    "auth-service" 
    "config-service"
    "metrics-service"
    "telemetry-service"
    "alerting-service"
    "dashboard-service"
    "nmt-service"
    "asr-service"
    "tts-service"
    "simple-ui-frontend"
    "postgres"
    "redis"
    "influxdb"
    "elasticsearch"
    "kafka"
    "zookeeper"
)

# Infrastructure services (don't need rebuilds)
INFRASTRUCTURE_SERVICES=("postgres" "redis" "influxdb" "elasticsearch" "kafka" "zookeeper")

# Microservices (need rebuilds)
MICROSERVICES=("api-gateway-service" "auth-service" "config-service" "metrics-service" "telemetry-service" "alerting-service" "dashboard-service" "nmt-service" "asr-service" "tts-service" "simple-ui-frontend")

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Docker Manager Script - Comprehensive Docker container management

USAGE:
    $0 <action> [options] [services]

ACTIONS:
    start       Start services (with optional rebuild)
    stop        Stop services
    restart     Restart services (with optional rebuild)
    rebuild     Rebuild and restart services
    update      Update services (rebuild if code changed)
    status      Show status of services
    logs        Show logs for services
    clean       Clean up stopped containers and unused images
    health      Check health of services

OPTIONS:
    -f, --force-rebuild    Force rebuild even if no changes detected
    -p, --parallel         Run operations in parallel (faster but more resource intensive)
    -v, --verbose          Verbose output
    -s, --skip-env         Skip environment file validation
    -h, --help             Show this help message

SERVICES:
    all                    All services (default)
    microservices          All microservices only
    infrastructure         Infrastructure services only
    <service-name>         Specific service(s)

EXAMPLES:
    # Start all services
    $0 start

    # Rebuild and restart specific services
    $0 rebuild api-gateway-service nmt-service

    # Update all microservices with force rebuild
    $0 update microservices --force-rebuild

    # Check status of all services
    $0 status

    # Show logs for specific service
    $0 logs nmt-service

    # Clean up Docker resources
    $0 clean

AVAILABLE SERVICES:
    Microservices: ${MICROSERVICES[*]}
    Infrastructure: ${INFRASTRUCTURE_SERVICES[*]}
EOF
}

# Function to validate service names
validate_services() {
    local services_to_validate=("$@")
    
    for service in "${services_to_validate[@]}"; do
        if [[ ! " ${ALL_SERVICES[@]} " =~ " ${service} " ]]; then
            print_error "Invalid service: '$service'"
            print_info "Available services: ${ALL_SERVICES[*]}"
            exit 1
        fi
    done
}

# Function to expand service groups
expand_service_groups() {
    local services=("$@")
    local expanded_services=()
    
    for service in "${services[@]}"; do
        case $service in
            "all")
                expanded_services+=("${ALL_SERVICES[@]}")
                ;;
            "microservices")
                expanded_services+=("${MICROSERVICES[@]}")
                ;;
            "infrastructure")
                expanded_services+=("${INFRASTRUCTURE_SERVICES[@]}")
                ;;
            *)
                expanded_services+=("$service")
                ;;
        esac
    done
    
    # Remove duplicates
    printf '%s\n' "${expanded_services[@]}" | sort -u
}

# Function to check environment files
check_env_files() {
    if [[ "$SKIP_ENV_CHECK" == "true" ]]; then
        return 0
    fi
    
    print_info "Checking environment files..."
    
    local missing_env_files=()
    
    # Check main .env file
    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        missing_env_files+=("$PROJECT_DIR/.env")
    fi
    
    # Check service-specific .env files
    for service in "${MICROSERVICES[@]}"; do
        # Skip env check for frontend services (they use different env handling)
        if [[ "$service" == "simple-ui-frontend" ]]; then
            continue
        fi
        
        local env_file="$PROJECT_DIR/services/$service/.env"
        if [[ ! -f "$env_file" ]]; then
            missing_env_files+=("$env_file")
        fi
    done
    
    if [[ ${#missing_env_files[@]} -gt 0 ]]; then
        print_warning "Missing environment files:"
        for file in "${missing_env_files[@]}"; do
            echo "  - $file"
        done
        print_info "You can copy from .env.template files or use --skip-env to continue"
        
        if [[ "$SKIP_ENV_CHECK" == "false" ]]; then
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        print_success "All environment files found"
    fi
}

# Function to check if service needs rebuild
needs_rebuild() {
    local service="$1"
    
    # Infrastructure services don't need rebuilds
    if [[ " ${INFRASTRUCTURE_SERVICES[@]} " =~ " ${service} " ]]; then
        return 1
    fi
    
    # Force rebuild if requested
    if [[ "$FORCE_REBUILD" == "true" ]]; then
        return 0
    fi
    
    # Check if service directory has changes
    local service_dir=""
    if [[ "$service" == "simple-ui-frontend" ]]; then
        service_dir="$PROJECT_DIR/frontend/simple-ui"
    else
        service_dir="$PROJECT_DIR/services/$service"
    fi
    
    if [[ -d "$service_dir" ]]; then
        # Simple check: if Dockerfile or requirements.txt/package.json changed
        local dockerfile="$service_dir/Dockerfile"
        local requirements="$service_dir/requirements.txt"
        local package_json="$service_dir/package.json"
        
        if [[ -f "$dockerfile" ]] || [[ -f "$requirements" ]] || [[ -f "$package_json" ]]; then
            return 0
        fi
    fi
    
    return 1
}

# Function to execute Docker Compose command
execute_docker_compose() {
    local cmd="$1"
    local services=("${@:2}")
    
    cd "$PROJECT_DIR"
    
    if [[ "$VERBOSE" == "true" ]]; then
        print_info "Executing: docker compose $cmd ${services[*]}"
    fi
    
    if [[ "$PARALLEL" == "true" && ${#services[@]} -gt 1 ]]; then
        # Run in parallel for multiple services
        local pids=()
        for service in "${services[@]}"; do
            (
                docker compose $cmd "$service" 2>&1 | while read line; do
                    echo "[$service] $line"
                done
            ) &
            pids+=($!)
        done
        
        # Wait for all parallel processes
        for pid in "${pids[@]}"; do
            wait "$pid"
        done
    else
        # Run sequentially
        docker compose $cmd "${services[@]}"
    fi
}

# Function to start services
start_services() {
    local services=("$@")
    
    print_info "Starting services: ${services[*]}"
    
    # Check environment files first
    check_env_files
    
    # Determine if rebuild is needed
    local services_to_rebuild=()
    local services_to_start=()
    
    for service in "${services[@]}"; do
        if needs_rebuild "$service"; then
            services_to_rebuild+=("$service")
        else
            services_to_start+=("$service")
        fi
    done
    
    # Start services that don't need rebuild
    if [[ ${#services_to_start[@]} -gt 0 ]]; then
        print_info "Starting services without rebuild: ${services_to_start[*]}"
        execute_docker_compose "up -d" "${services_to_start[@]}"
    fi
    
    # Rebuild and start services that need rebuild
    if [[ ${#services_to_rebuild[@]} -gt 0 ]]; then
        print_info "Rebuilding and starting services: ${services_to_rebuild[*]}"
        execute_docker_compose "up -d --build" "${services_to_rebuild[@]}"
    fi
    
    print_success "Services started successfully"
}

# Function to stop services
stop_services() {
    local services=("$@")
    
    print_info "Stopping services: ${services[*]}"
    execute_docker_compose "stop" "${services[@]}"
    print_success "Services stopped successfully"
}

# Function to restart services
restart_services() {
    local services=("$@")
    
    print_info "Restarting services: ${services[*]}"
    
    # Check if rebuild is needed
    local services_to_rebuild=()
    local services_to_restart=()
    
    for service in "${services[@]}"; do
        if needs_rebuild "$service"; then
            services_to_rebuild+=("$service")
        else
            services_to_restart+=("$service")
        fi
    done
    
    # Restart services that don't need rebuild
    if [[ ${#services_to_restart[@]} -gt 0 ]]; then
        print_info "Restarting services without rebuild: ${services_to_restart[*]}"
        execute_docker_compose "restart" "${services_to_restart[@]}"
    fi
    
    # Rebuild and restart services that need rebuild
    if [[ ${#services_to_rebuild[@]} -gt 0 ]]; then
        print_info "Rebuilding and restarting services: ${services_to_rebuild[*]}"
        execute_docker_compose "up -d --build" "${services_to_rebuild[@]}"
    fi
    
    print_success "Services restarted successfully"
}

# Function to rebuild services
rebuild_services() {
    local services=("$@")
    
    print_info "Rebuilding services: ${services[*]}"
    check_env_files
    execute_docker_compose "up -d --build" "${services[@]}"
    print_success "Services rebuilt successfully"
}

# Function to update services
update_services() {
    local services=("$@")
    
    print_info "Updating services: ${services[*]}"
    
    # Check environment files
    check_env_files
    
    # Determine which services need rebuild
    local services_to_rebuild=()
    local services_to_restart=()
    
    for service in "${services[@]}"; do
        if needs_rebuild "$service"; then
            services_to_rebuild+=("$service")
        else
            services_to_restart+=("$service")
        fi
    done
    
    # Restart services that don't need rebuild
    if [[ ${#services_to_restart[@]} -gt 0 ]]; then
        print_info "Restarting services without rebuild: ${services_to_restart[*]}"
        execute_docker_compose "restart" "${services_to_restart[@]}"
    fi
    
    # Rebuild services that need rebuild
    if [[ ${#services_to_rebuild[@]} -gt 0 ]]; then
        print_info "Rebuilding services: ${services_to_rebuild[*]}"
        execute_docker_compose "up -d --build" "${services_to_rebuild[@]}"
    fi
    
    print_success "Services updated successfully"
}

# Function to show status
show_status() {
    local services=("$@")
    
    print_info "Service Status:"
    cd "$PROJECT_DIR"
    docker compose ps "${services[@]}"
}

# Function to show logs
show_logs() {
    local services=("$@")
    
    print_info "Showing logs for services: ${services[*]}"
    cd "$PROJECT_DIR"
    docker compose logs -f "${services[@]}"
}

# Function to clean up Docker resources
clean_docker() {
    print_info "Cleaning up Docker resources..."
    
    # Remove stopped containers
    print_info "Removing stopped containers..."
    docker container prune -f
    
    # Remove unused images
    print_info "Removing unused images..."
    docker image prune -f
    
    # Remove unused volumes (optional)
    read -p "Remove unused volumes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker volume prune -f
    fi
    
    print_success "Docker cleanup completed"
}

# Function to check health
check_health() {
    local services=("$@")
    
    print_info "Checking health of services: ${services[*]}"
    
    cd "$PROJECT_DIR"
    
    for service in "${services[@]}"; do
        local status=$(docker compose ps --format "table {{.Service}}\t{{.Status}}" "$service" | tail -n +2)
        if [[ -n "$status" ]]; then
            echo "$status"
        else
            print_warning "Service $service not found"
        fi
    done
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--force-rebuild)
                FORCE_REBUILD=true
                shift
                ;;
            -p|--parallel)
                PARALLEL=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -s|--skip-env)
                SKIP_ENV_CHECK=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            start|stop|restart|rebuild|update|status|logs|clean|health)
                if [[ -z "$ACTION" ]]; then
                    ACTION="$1"
                else
                    SERVICES+=("$1")
                fi
                shift
                ;;
            *)
                SERVICES+=("$1")
                shift
                ;;
        esac
    done
}

# Main function
main() {
    # Parse arguments
    parse_arguments "$@"
    
    # Validate action
    if [[ -z "$ACTION" ]]; then
        print_error "No action specified"
        show_usage
        exit 1
    fi
    
    # Set default services if none specified
    if [[ ${#SERVICES[@]} -eq 0 ]]; then
        SERVICES=("all")
    fi
    
    # Expand service groups
    SERVICES=($(expand_service_groups "${SERVICES[@]}"))
    
    # Validate services
    validate_services "${SERVICES[@]}"
    
    # Execute action
    case $ACTION in
        start)
            start_services "${SERVICES[@]}"
            ;;
        stop)
            stop_services "${SERVICES[@]}"
            ;;
        restart)
            restart_services "${SERVICES[@]}"
            ;;
        rebuild)
            rebuild_services "${SERVICES[@]}"
            ;;
        update)
            update_services "${SERVICES[@]}"
            ;;
        status)
            show_status "${SERVICES[@]}"
            ;;
        logs)
            show_logs "${SERVICES[@]}"
            ;;
        clean)
            clean_docker
            ;;
        health)
            check_health "${SERVICES[@]}"
            ;;
        *)
            print_error "Unknown action: $ACTION"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
