#!/bin/bash
# Create default platform Kafka topics for local Docker Compose.
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:9092}"
BIN=/opt/kafka/bin

echo "Waiting for Kafka at ${BOOTSTRAP}..."
for i in $(seq 1 60); do
  if "${BIN}/kafka-broker-api-versions.sh" --bootstrap-server "${BOOTSTRAP}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

create_topic() {
  local name="$1"
  local partitions="${2:-3}"
  echo "Ensuring topic: ${name} (partitions=${partitions})"
  "${BIN}/kafka-topics.sh" --bootstrap-server "${BOOTSTRAP}" \
    --create --if-not-exists \
    --topic "${name}" \
    --partitions "${partitions}" \
    --replication-factor 1 \
    --config retention.ms=604800000 \
    --config compression.type=gzip \
    --config cleanup.policy=delete || true
}

create_topic "notification_alerts.events" 3
create_topic "kafka-topic-otel-trace" 3

"${BIN}/kafka-topics.sh" --bootstrap-server "${BOOTSTRAP}" --list
echo "Kafka topic init complete."
