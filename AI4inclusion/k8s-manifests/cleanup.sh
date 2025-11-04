#!/bin/bash

# AI4Inclusion Kubernetes Cleanup Script
# This script removes all deployed resources from the dev namespace

set -e

echo "🧹 Starting AI4Inclusion Kubernetes Cleanup..."

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl is not installed or not in PATH"
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster"
    exit 1
fi

echo "✅ Kubernetes cluster is accessible"

# Check if dev namespace exists
if ! kubectl get namespace dev &> /dev/null; then
    echo "ℹ️  Dev namespace does not exist, nothing to clean up"
    exit 0
fi

echo "📦 Found dev namespace, proceeding with cleanup..."

# Delete all deployments
echo "🗑️  Deleting deployments..."
kubectl delete deployment --all -n dev --ignore-not-found=true

# Delete all services
echo "🗑️  Deleting services..."
kubectl delete service --all -n dev --ignore-not-found=true

# Delete all configmaps
echo "🗑️  Deleting configmaps..."
kubectl delete configmap --all -n dev --ignore-not-found=true

# Delete all secrets
echo "🗑️  Deleting secrets..."
kubectl delete secret --all -n dev --ignore-not-found=true

# Delete all persistent volume claims
echo "🗑️  Deleting persistent volume claims..."
kubectl delete pvc --all -n dev --ignore-not-found=true

# Wait for resources to be deleted
echo "⏳ Waiting for resources to be deleted..."
sleep 10

# Delete the namespace
echo "🗑️  Deleting dev namespace..."
kubectl delete namespace dev --ignore-not-found=true

echo "✅ Cleanup completed successfully!"
echo ""
echo "All AI4Inclusion resources have been removed from the cluster."
