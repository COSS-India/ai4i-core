#!/bin/bash

# Service Deployment Script
set -e

SERVICE_NAME=$(basename $(pwd))
echo "🚀 Deploying $SERVICE_NAME..."

# Apply all manifests in the current directory
kubectl apply -f .

# Wait for deployment to be ready (if it's a deployment)
if kubectl get deployment $SERVICE_NAME -n dev &> /dev/null; then
    echo "⏳ Waiting for $SERVICE_NAME to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/$SERVICE_NAME -n dev
fi

# Check status
echo "✅ $SERVICE_NAME deployed successfully!"
kubectl get pods -n dev -l app=$SERVICE_NAME 2>/dev/null || echo "No pods found for $SERVICE_NAME"
kubectl get services -n dev -l app=$SERVICE_NAME 2>/dev/null || echo "No services found for $SERVICE_NAME"
