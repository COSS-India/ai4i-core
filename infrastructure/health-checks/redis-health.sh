#!/bin/bash

# Redis health check script
# This script checks if Redis is healthy and operational

set -e

echo "Checking Redis health..."

# Check if Redis is responding to ping
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" ping > /dev/null 2>&1; then
    echo "Redis is not responding to ping"
    exit 1
fi

# Verify authentication works
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" auth "${REDIS_PASSWORD}" > /dev/null 2>&1; then
    echo "Redis authentication failed"
    exit 1
fi

# Test basic operations
TEST_KEY="health_check_test_$(date +%s)"
TEST_VALUE="test_value"

# Set a test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" set "$TEST_KEY" "$TEST_VALUE" > /dev/null 2>&1; then
    echo "Failed to set test key"
    exit 1
fi

# Get the test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" get "$TEST_KEY" | grep -q "$TEST_VALUE"; then
    echo "Failed to get test key"
    exit 1
fi

# Delete the test key
if ! redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" del "$TEST_KEY" > /dev/null 2>&1; then
    echo "Failed to delete test key"
    exit 1
fi

# Check memory usage
MEMORY_USAGE=$(redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
MEMORY_PERCENT=$(redis-cli -h localhost -p 6379 -a "${REDIS_PASSWORD}" info memory | grep used_memory_percentage | cut -d: -f2 | tr -d '\r')

echo "Redis memory usage: $MEMORY_USAGE ($MEMORY_PERCENT%)"

# Check if memory usage is below critical threshold (90%)
if [ "$MEMORY_PERCENT" -gt 90 ]; then
    echo "Redis memory usage is critical: $MEMORY_PERCENT%"
    exit 1
fi

echo "Redis is healthy and operational"
exit 0
