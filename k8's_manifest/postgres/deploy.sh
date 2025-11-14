#!/bin/bash

# PostgreSQL Deployment Script
set -e

echo "🐘 Deploying PostgreSQL..."

# Apply manifests in order
kubectl apply -f postgres-pvc.yaml
kubectl apply -f postgres-configmap.yaml
kubectl apply -f postgres-secret.yaml
kubectl apply -f postgres-service.yaml
kubectl apply -f postgres-deployment.yaml

# Wait for deployment to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/postgres -n dev

# Check status
echo "✅ PostgreSQL deployed successfully!"
kubectl get pods -n dev -l app=postgres
kubectl get services -n dev -l app=postgres
