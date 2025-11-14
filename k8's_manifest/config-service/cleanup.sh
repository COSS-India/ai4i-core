#!/bin/bash

# Service Cleanup Script
set -e

SERVICE_NAME=$(basename $(pwd))
echo "🧹 Cleaning up $SERVICE_NAME..."

# Delete all resources in the current directory
kubectl delete -f . --ignore-not-found=true

echo "✅ $SERVICE_NAME cleaned up successfully!"
