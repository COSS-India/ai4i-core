#!/bin/bash

# InfluxDB health check script
# This script checks if InfluxDB is healthy and operational

set -e

echo "Checking InfluxDB health..."

# Check InfluxDB health endpoint
if ! curl -f -s http://localhost:8086/health > /dev/null 2>&1; then
    echo "InfluxDB health endpoint is not responding"
    exit 1
fi

# Verify API is responding
if ! curl -f -s http://localhost:8086/api/v2/ping > /dev/null 2>&1; then
    echo "InfluxDB API is not responding"
    exit 1
fi

# Check that required buckets exist
REQUIRED_BUCKETS=("metrics" "metrics-aggregated" "system-metrics")
INFLUXDB_TOKEN="${INFLUXDB_ADMIN_TOKEN:-dhruva-influx-token-2024}"
INFLUXDB_ORG="${INFLUXDB_ORG:-dhruva-org}"

for bucket in "${REQUIRED_BUCKETS[@]}"; do
    if ! curl -f -s -H "Authorization: Token $INFLUXDB_TOKEN" \
        "http://localhost:8086/api/v2/buckets?org=$INFLUXDB_ORG" | \
        grep -q "\"name\":\"$bucket\""; then
        echo "Required bucket $bucket does not exist"
        exit 1
    fi
done

# Check that organization is configured
if ! curl -f -s -H "Authorization: Token $INFLUXDB_TOKEN" \
    "http://localhost:8086/api/v2/orgs" | \
    grep -q "\"name\":\"$INFLUXDB_ORG\""; then
    echo "Required organization $INFLUXDB_ORG does not exist"
    exit 1
fi

echo "InfluxDB is healthy and all required buckets exist"
exit 0
