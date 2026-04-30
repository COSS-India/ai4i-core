#!/bin/bash

# Kafka health check script
# This script checks if Kafka is healthy and operational

set -e

echo "Checking Kafka health..."

# Check if Kafka broker is responding
if ! kafka-broker-api-versions --bootstrap-server kafka:9092 > /dev/null 2>&1; then
    echo "Kafka broker is not responding"
    exit 1
fi

# Check that required topics exist
REQUIRED_TOPICS=("config-updates" "logs" "traces" "metrics" "alerts")

for topic in "${REQUIRED_TOPICS[@]}"; do
    if ! kafka-topics --bootstrap-server kafka:9092 --list | grep -q "$topic"; then
        echo "Required topic $topic does not exist"
        exit 1
    fi
done

# Check that Zookeeper connection is healthy
if ! kafka-topics --bootstrap-server kafka:9092 --list > /dev/null 2>&1; then
    echo "Zookeeper connection is not healthy"
    exit 1
fi

# Verify broker is in the ISR (In-Sync Replicas) list
for topic in "${REQUIRED_TOPICS[@]}"; do
    ISR_COUNT=$(kafka-topics --bootstrap-server kafka:9092 --describe --topic "$topic" | \
        grep -o "Isr: [0-9]*" | cut -d' ' -f2 | wc -l)
    
    if [ "$ISR_COUNT" -eq 0 ]; then
        echo "Topic $topic has no in-sync replicas"
        exit 1
    fi
done

# Test producing and consuming a message
TEST_TOPIC="health-check-topic"
TEST_MESSAGE="health-check-message-$(date +%s)"

# Create test topic if it doesn't exist
kafka-topics --bootstrap-server kafka:9092 --create --topic "$TEST_TOPIC" --partitions 1 --replication-factor 1 --if-not-exists > /dev/null 2>&1

# Produce test message
echo "$TEST_MESSAGE" | kafka-console-producer --bootstrap-server kafka:9092 --topic "$TEST_TOPIC" > /dev/null 2>&1

# Consume test message
CONSUMED_MESSAGE=$(timeout 10s kafka-console-consumer --bootstrap-server kafka:9092 --topic "$TEST_TOPIC" --from-beginning --max-messages 1 2>/dev/null | head -1)

if [ "$CONSUMED_MESSAGE" != "$TEST_MESSAGE" ]; then
    echo "Failed to produce and consume test message"
    exit 1
fi

# Clean up test topic
kafka-topics --bootstrap-server kafka:9092 --delete --topic "$TEST_TOPIC" > /dev/null 2>&1

echo "Kafka is healthy and all required topics exist"
exit 0
