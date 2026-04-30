#!/bin/bash

# Stop all services gracefully
# This script stops all services and optionally removes volumes

set -e

echo "Stopping Dhruva Microservices Platform..."

# Change to project directory
cd "$(dirname "$0")/.."

# Parse command line arguments
REMOVE_VOLUMES=false
REMOVE_ORPHANS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --volumes)
            REMOVE_VOLUMES=true
            shift
            ;;
        --remove-orphans)
            REMOVE_ORPHANS=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--volumes] [--remove-orphans]"
            echo "  --volumes        Remove volumes when stopping"
            echo "  --remove-orphans Remove orphaned containers"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Stop all services
echo "Stopping all services..."
if [ "$REMOVE_VOLUMES" = true ] && [ "$REMOVE_ORPHANS" = true ]; then
    sudo docker compose down --volumes --remove-orphans
elif [ "$REMOVE_VOLUMES" = true ]; then
    sudo docker compose down --volumes
elif [ "$REMOVE_ORPHANS" = true ]; then
    sudo docker compose down --remove-orphans
else
    sudo docker compose down
fi

echo "All services stopped successfully!"

if [ "$REMOVE_VOLUMES" = true ]; then
    echo "Volumes have been removed. You will need to reinitialize the infrastructure."
fi

echo ""
echo "To start all services again: ./scripts/start-all.sh"
echo "To start with fresh data: ./scripts/stop-all.sh --volumes && ./scripts/start-all.sh"
