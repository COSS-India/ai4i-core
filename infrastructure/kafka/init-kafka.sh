#!/bin/bash

# Initialize Kafka topics with appropriate partitions and replication factors
# This script is executed when the Kafka container starts

set -e

echo "Starting Kafka initialization..."

# Wait for Kafka to be ready
echo "Waiting for Kafka to be ready..."
until kafka-broker-api-versions --bootstrap-server kafka:9092; do
    echo "Kafka is not ready yet, waiting..."
    sleep 5
done

echo "Kafka is ready, starting initialization..."

# Set environment variables
KAFKA_BOOTSTRAP_SERVERS="kafka:9092"
REPLICATION_FACTOR=1

# Create topics with appropriate settings
echo "Creating Kafka topics..."

# Config updates topic
echo "Creating topic: config-updates"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic config-updates \
    --partitions 3 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic config-updates already exists"

# Logs topic
echo "Creating topic: logs"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic logs \
    --partitions 5 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic logs already exists"

# Traces topic
echo "Creating topic: traces"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic traces \
    --partitions 5 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic traces already exists"

# Metrics topic
echo "Creating topic: metrics"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic metrics \
    --partitions 10 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=2592000000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic metrics already exists"

# Alerts topic
echo "Creating topic: alerts"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic alerts \
    --partitions 3 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic alerts already exists"

# Create consumer groups for each service
echo "Creating consumer groups..."

# Config service consumer group
echo "Creating consumer group: config-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group config-service \
    --describe || echo "Consumer group config-service already exists"

# Telemetry service consumer group
echo "Creating consumer group: telemetry-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group telemetry-service \
    --describe || echo "Consumer group telemetry-service already exists"

# Alerting service consumer group
echo "Creating consumer group: alerting-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group alerting-service \
    --describe || echo "Consumer group alerting-service already exists"

# List all topics to verify creation
echo "Listing all topics:"
kafka-topics --list --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS

# Describe topics to show configuration
echo "Describing topics:"
kafka-topics --describe --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS

echo "Kafka initialization completed successfully!"

# Test the setup by producing and consuming a test message
echo "Testing Kafka setup..."
echo "test-message" | kafka-console-producer --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS --topic config-updates
kafka-console-consumer --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS --topic config-updates --from-beginning --max-messages 1 --timeout-ms 5000 || echo "Failed to consume test message"

echo "Kafka is ready for use!"
