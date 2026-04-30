#!/bin/bash

# Initialize InfluxDB with buckets, retention policies, and API tokens
# This script is executed when the InfluxDB container starts

set -e

echo "Starting InfluxDB initialization..."

# Wait for InfluxDB to be ready
echo "Waiting for InfluxDB to be ready..."
until curl -f http://localhost:8086/health; do
    echo "InfluxDB is not ready yet, waiting..."
    sleep 2
done

echo "InfluxDB is ready, starting initialization..."

# Set environment variables
INFLUXDB_URL="http://localhost:8086"
INFLUXDB_ADMIN_USER="${INFLUXDB_ADMIN_USER:-admin}"
INFLUXDB_ADMIN_PASSWORD="${INFLUXDB_ADMIN_PASSWORD:-influx_secure_password_2024}"
INFLUXDB_ORG="${INFLUXDB_ORG:-dhruva-org}"
INFLUXDB_BUCKET="${INFLUXDB_BUCKET:-metrics}"
INFLUXDB_ADMIN_TOKEN="${INFLUXDB_ADMIN_TOKEN:-dhruva-influx-token-2024}"

# Create organization if it doesn't exist
echo "Creating organization: $INFLUXDB_ORG"
influx org create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --name $INFLUXDB_ORG \
    || echo "Organization $INFLUXDB_ORG already exists"

# Create buckets with retention policies
echo "Creating bucket: metrics (90 days retention)"
influx bucket create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name metrics \
    --retention 90d \
    || echo "Bucket metrics already exists"

echo "Creating bucket: metrics-aggregated (365 days retention)"
influx bucket create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name metrics-aggregated \
    --retention 365d \
    || echo "Bucket metrics-aggregated already exists"

echo "Creating bucket: system-metrics (30 days retention)"
influx bucket create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name system-metrics \
    --retention 30d \
    || echo "Bucket system-metrics already exists"

# Create API tokens for each microservice
echo "Creating API tokens for microservices..."

# Metrics service token
echo "Creating token for metrics-service..."
influx auth create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --all-access \
    --description "Metrics Service Token" \
    || echo "Metrics service token already exists"

# Dashboard service token
echo "Creating token for dashboard-service..."
influx auth create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --read-buckets \
    --description "Dashboard Service Token" \
    || echo "Dashboard service token already exists"

# Create continuous queries for data aggregation
echo "Creating continuous queries for data aggregation..."

# Hourly aggregation query
influx query create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name "hourly_metrics_aggregation" \
    --query "from(bucket: \"metrics\")
    |> range(start: -1h)
    |> filter(fn: (r) => r[\"_measurement\"] == \"api_requests\")
    |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
    |> to(bucket: \"metrics-aggregated\", org: \"$INFLUXDB_ORG\")" \
    || echo "Hourly aggregation query already exists"

# Daily aggregation query
influx query create \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name "daily_metrics_aggregation" \
    --query "from(bucket: \"metrics\")
    |> range(start: -24h)
    |> filter(fn: (r) => r[\"_measurement\"] == \"api_requests\")
    |> aggregateWindow(every: 24h, fn: mean, createEmpty: false)
    |> to(bucket: \"metrics-aggregated\", org: \"$INFLUXDB_ORG\")" \
    || echo "Daily aggregation query already exists"

# Set up retention policies for automatic data cleanup
echo "Setting up retention policies..."

# Create retention policy for metrics bucket
influx bucket update \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name metrics \
    --retention 90d \
    || echo "Retention policy for metrics already set"

# Create retention policy for aggregated metrics bucket
influx bucket update \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name metrics-aggregated \
    --retention 365d \
    || echo "Retention policy for metrics-aggregated already set"

# Create retention policy for system metrics bucket
influx bucket update \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    --name system-metrics \
    --retention 30d \
    || echo "Retention policy for system-metrics already set"

echo "InfluxDB initialization completed successfully!"

# Test the setup
echo "Testing InfluxDB setup..."
influx query \
    --host $INFLUXDB_URL \
    --token $INFLUXDB_ADMIN_TOKEN \
    --org $INFLUXDB_ORG \
    'buckets()' \
    || echo "Failed to test InfluxDB setup"

echo "InfluxDB is ready for use!"
