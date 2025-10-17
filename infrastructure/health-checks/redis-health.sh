#!/bin/bash

# Redis health check script
# This script checks if Redis is healthy and operational

set -e

echo "Checking Redis health..."

# Check if Redis is responding to ping
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" ping > /dev/null 2>&1; then
    echo "Redis is not responding to ping"
    exit 1
fi

# Verify authentication works
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" auth "${REDIS_PASSWORD:-redis_secure_password_2024}" > /dev/null 2>&1; then
    echo "Redis authentication failed"
    exit 1
fi

# Test basic operations
TEST_KEY="health_check_test_$(date +%s)"
TEST_VALUE="test_value"

# Set a test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" set "$TEST_KEY" "$TEST_VALUE" > /dev/null 2>&1; then
    echo "Failed to set test key"
    exit 1
fi

# Get the test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" get "$TEST_KEY" | grep -q "$TEST_VALUE"; then
    echo "Failed to get test key"
    exit 1
fi

# Delete the test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" del "$TEST_KEY" > /dev/null 2>&1; then
    echo "Failed to delete test key"
    exit 1
fi

# Check memory usage
MEMORY_USAGE=$(redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
MEMORY_PERCENT=$(redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD:-redis_secure_password_2024}" info memory | grep used_memory_percentage | cut -d: -f2 | tr -d '\r')

echo "Redis memory usage: $MEMORY_USAGE ($MEMORY_PERCENT%)"

# Check if memory usage is below critical threshold (90%)
if [ "$MEMORY_PERCENT" -gt 90 ]; then
    echo "Redis memory usage is critical: $MEMORY_PERCENT%"
    exit 1
fi

echo "Redis is healthy and operational"
exit 0
