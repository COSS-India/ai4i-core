#!/bin/bash

# Initialize all infrastructure components
# This script runs all infrastructure initialization scripts

set -e

echo "Initializing infrastructure components..."

# Change to project directory
cd "$(dirname "$0")/.."

# Wait for all infrastructure services to be healthy
echo "Waiting for infrastructure services to be healthy..."

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until docker-compose exec postgres pg_isready -U "${POSTGRES_USER:-dhruva_user}" > /dev/null 2>&1; do
    echo "PostgreSQL is not ready yet, waiting..."
    sleep 5
done
echo "PostgreSQL is ready"

# Wait for Redis
echo "Waiting for Redis..."
until docker-compose exec redis redis-cli -a "${REDIS_PASSWORD:-redis_secure_password_2024}" ping > /dev/null 2>&1; do
    echo "Redis is not ready yet, waiting..."
    sleep 5
done
echo "Redis is ready"

# Wait for InfluxDB
echo "Waiting for InfluxDB..."
until curl -f http://localhost:8086/health > /dev/null 2>&1; do
    echo "InfluxDB is not ready yet, waiting..."
    sleep 5
done
echo "InfluxDB is ready"

# Wait for Elasticsearch
echo "Waiting for Elasticsearch..."
until curl -f -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" http://localhost:9200/_cluster/health > /dev/null 2>&1; do
    echo "Elasticsearch is not ready yet, waiting..."
    sleep 5
done
echo "Elasticsearch is ready"

# Wait for Kafka
echo "Waiting for Kafka..."
until kafka-broker-api-versions --bootstrap-server localhost:9092 > /dev/null 2>&1; do
    echo "Kafka is not ready yet, waiting..."
    sleep 5
done
echo "Kafka is ready"

# Run PostgreSQL initialization
echo "Running PostgreSQL initialization..."
if [ -f "infrastructure/postgres/init-databases.sql" ]; then
    echo "PostgreSQL databases and schemas are automatically initialized via Docker volume mount"
    echo "PostgreSQL initialization completed"
else
    echo "Warning: PostgreSQL initialization script not found"
fi

# Run InfluxDB initialization
echo "Running InfluxDB initialization..."
if [ -f "infrastructure/influxdb/init-influxdb.sh" ]; then
    docker-compose exec influxdb /bin/bash /docker-entrypoint-initdb.d/init-influxdb.sh
    echo "InfluxDB initialization completed"
else
    echo "Warning: InfluxDB initialization script not found"
fi

# Run Elasticsearch initialization
echo "Running Elasticsearch initialization..."
if [ -f "infrastructure/elasticsearch/init-elasticsearch.sh" ]; then
    docker-compose exec elasticsearch /bin/bash /docker-entrypoint-initdb.d/init-elasticsearch.sh
    echo "Elasticsearch initialization completed"
else
    echo "Warning: Elasticsearch initialization script not found"
fi

# Run Kafka initialization
echo "Running Kafka initialization..."
if [ -f "infrastructure/kafka/init-kafka.sh" ]; then
    docker-compose exec kafka /bin/bash /docker-entrypoint-initdb.d/init-kafka.sh
    echo "Kafka initialization completed"
else
    echo "Warning: Kafka initialization script not found"
fi

# Verify all initialization completed successfully
echo "Verifying infrastructure initialization..."

# Check PostgreSQL databases
echo "Checking PostgreSQL databases..."
REQUIRED_DATABASES=("auth_db" "config_db" "metrics_db" "telemetry_db" "alerting_db" "dashboard_db")
for db in "${REQUIRED_DATABASES[@]}"; do
    if docker-compose exec postgres psql -U "${POSTGRES_USER:-dhruva_user}" -d "$db" -c "SELECT 1;" > /dev/null 2>&1; then
        echo "✓ Database $db is accessible"
    else
        echo "✗ Database $db is not accessible"
        exit 1
    fi
done

# Check InfluxDB buckets
echo "Checking InfluxDB buckets..."
REQUIRED_BUCKETS=("metrics" "metrics-aggregated" "system-metrics")
for bucket in "${REQUIRED_BUCKETS[@]}"; do
    if curl -s -H "Authorization: Token ${INFLUXDB_ADMIN_TOKEN:-dhruva-influx-token-2024}" \
        "http://localhost:8086/api/v2/buckets?org=${INFLUXDB_ORG:-dhruva-org}" | \
        grep -q "\"name\":\"$bucket\""; then
        echo "✓ Bucket $bucket exists"
    else
        echo "✗ Bucket $bucket does not exist"
        exit 1
    fi
done

# Check Elasticsearch indices
echo "Checking Elasticsearch indices..."
REQUIRED_INDICES=("logs" "traces")
for index in "${REQUIRED_INDICES[@]}"; do
    if curl -s -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" \
        http://localhost:9200/_cat/indices | grep -q "$index"; then
        echo "✓ Index $index exists"
    else
        echo "✗ Index $index does not exist"
        exit 1
    fi
done

# Check Kafka topics
echo "Checking Kafka topics..."
REQUIRED_TOPICS=("config-updates" "logs" "traces" "metrics" "alerts")
for topic in "${REQUIRED_TOPICS[@]}"; do
    if kafka-topics --bootstrap-server localhost:9092 --list | grep -q "$topic"; then
        echo "✓ Topic $topic exists"
    else
        echo "✗ Topic $topic does not exist"
        exit 1
    fi
done

echo ""
echo "Infrastructure initialization completed successfully!"
echo "All databases, buckets, indices, and topics are ready for use."
