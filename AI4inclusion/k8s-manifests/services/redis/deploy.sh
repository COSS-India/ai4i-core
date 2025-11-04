#!/bin/bash

# Redis Deployment Script
set -e

echo "🔴 Deploying Redis..."

# Apply manifests in order
kubectl apply -f redis-pvc.yaml
kubectl apply -f redis-secret.yaml
kubectl apply -f redis-service.yaml
kubectl apply -f redis-deployment.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for Redis to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/redis -n dev

# Check status
echo "✅ Redis deployed successfully!"
kubectl get pods -n dev -l app=redis
kubectl get services -n dev -l app=redis
