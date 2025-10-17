#!/bin/bash

# Test execution script for Dhruva Microservices Platform

set -e  # Exit on error

echo "========================================"
echo "Dhruva Microservices - Test Suite"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
TEST_TYPE="${1:-all}"  # Default to all tests
COVERAGE="${2:-false}" # Default no coverage

# Check if services are running
echo "Checking if services are running..."
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${RED}Error: Services are not running. Start services first with: docker-compose up -d${NC}"
    exit 1
fi

echo -e "${GREEN}Services are running${NC}"
echo ""

# Install test dependencies if not already installed
if [ ! -d "tests/venv" ]; then
    echo "Installing test dependencies..."
    cd tests
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
else
    source tests/venv/bin/activate
fi

# Run tests based on type
case "$TEST_TYPE" in
    unit)
        echo "Running unit tests..."
        pytest -m unit -v
        ;;
    integration)
        echo "Running integration tests..."
        pytest -m integration -v
        ;;
    e2e)
        echo "Running end-to-end tests..."
        pytest -m e2e -v
        ;;
    streaming)
        echo "Running WebSocket streaming tests..."
        pytest -m streaming -v
        ;;
    all)
        echo "Running all tests..."
        if [ "$COVERAGE" = "true" ]; then
            pytest --cov=services --cov-report=html --cov-report=term-missing -v
            echo ""
            echo -e "${GREEN}Coverage report generated: htmlcov/index.html${NC}"
        else
            pytest -v
        fi
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo "Usage: ./scripts/run-tests.sh [unit|integration|e2e|streaming|all] [coverage]"
        exit 1
        ;;
esac

# Deactivate virtual environment
deactivate

echo ""
echo -e "${GREEN}Tests completed successfully!${NC}"

