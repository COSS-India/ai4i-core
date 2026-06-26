#!/bin/bash

# Initialize Kafka topics with appropriate partitions and replication factors
# This script is executed when the Kafka container starts
#
# Overridable via environment variables:
#   KAFKA_BOOTSTRAP_SERVERS  (default: localhost:9093)
#   REPLICATION_FACTOR       (default: 1)

set -e

KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-localhost:9093}"
REPLICATION_FACTOR="${REPLICATION_FACTOR:-1}"

echo "Starting Kafka initialization..."
echo "  Bootstrap servers : $KAFKA_BOOTSTRAP_SERVERS"
echo "  Replication factor: $REPLICATION_FACTOR"

echo "Waiting for Kafka to be ready..."
until kafka-broker-api-versions --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS; do
    echo "Kafka is not ready yet, waiting..."
    sleep 5
done

echo "Kafka is ready, starting initialization..."

echo "Creating Kafka topics..."

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

echo "Creating topic: usage"
kafka-topics --create \
    --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --topic usage \
    --partitions 10 \
    --replication-factor $REPLICATION_FACTOR \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete \
    --if-not-exists || echo "Topic alerts already exists"

echo "Creating consumer groups..."

echo "Creating consumer group: config-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group config-service \
    --describe || echo "Consumer group config-service already exists"

echo "Creating consumer group: telemetry-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group telemetry-service \
    --describe || echo "Consumer group telemetry-service already exists"

echo "Creating consumer group: alerting-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group alerting-service \
    --describe || echo "Consumer group alerting-service already exists"

echo "Creating consumer group: ppu-usage-service"
kafka-consumer-groups --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS \
    --group ppu-usage-service \
    --describe || echo "Consumer group ppu-usage-service already exists"

echo "Listing all topics:"
kafka-topics --list --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS

echo "Describing topics:"
kafka-topics --describe --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS

echo "Kafka initialization completed successfully!"

echo "Testing Kafka setup..."
echo "test-message" | kafka-console-producer --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS --topic config-updates
kafka-console-consumer --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS --topic config-updates --from-beginning --max-messages 1 --timeout-ms 5000 || echo "Failed to consume test message"

echo "Kafka is ready for use!"
