#!/bin/bash
# Test runner script for feature flag tests

set -e

echo "Running feature flag tests..."

# Set test environment variables
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@localhost:5432/config_db_test}"
export TEST_REDIS_URL="${TEST_REDIS_URL:-redis://localhost:6379/2}"

# Run tests
pytest tests/test_feature_flags.py -v --tb=short

# Run with coverage if coverage is installed
if command -v pytest-cov &> /dev/null; then
    echo ""
    echo "Running tests with coverage..."
    pytest tests/test_feature_flags.py -v --cov=. --cov-report=html --cov-report=term
fi

echo "Tests completed!"

