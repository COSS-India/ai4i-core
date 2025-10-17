#!/bin/bash

# Elasticsearch health check script
# This script checks if Elasticsearch is healthy and operational

set -e

echo "Checking Elasticsearch health..."

# Check Elasticsearch cluster health
CLUSTER_HEALTH=$(curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
    http://localhost:9200/_cluster/health | \
    grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$CLUSTER_HEALTH" != "green" ] && [ "$CLUSTER_HEALTH" != "yellow" ]; then
    echo "Elasticsearch cluster status is $CLUSTER_HEALTH (not green or yellow)"
    exit 1
fi

# Check that required indices exist
REQUIRED_INDICES=("logs" "traces")

for index in "${REQUIRED_INDICES[@]}"; do
    if ! curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
        http://localhost:9200/_cat/indices | \
        grep -q "$index"; then
        echo "Required index $index does not exist"
        exit 1
    fi
done

# Verify that index templates are configured
if ! curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
    http://localhost:9200/_index_template | \
    grep -q "logs_template"; then
    echo "Logs index template is not configured"
    exit 1
fi

if ! curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
    http://localhost:9200/_index_template | \
    grep -q "traces_template"; then
    echo "Traces index template is not configured"
    exit 1
fi

# Check node availability
NODE_COUNT=$(curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
    http://localhost:9200/_cat/nodes | wc -l)

if [ "$NODE_COUNT" -eq 0 ]; then
    echo "No Elasticsearch nodes are available"
    exit 1
fi

echo "Elasticsearch is healthy and all required indices exist"
exit 0
