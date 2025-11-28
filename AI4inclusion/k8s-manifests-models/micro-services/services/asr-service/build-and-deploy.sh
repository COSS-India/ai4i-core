#!/bin/bash

# ASR Service - Build and Deploy Script
# This script builds the Docker image and deploys it to Kubernetes

set -e  # Exit on error

# Configuration
SERVICE_DIR="/home/ubuntu/AI4inclusion/k8s-manifests-models/micro-services/services/asr-service"
AWS_ACCOUNT_ID="662074586476"
AWS_REGION="ap-south-1"
IMAGE_NAME="ai4voice/asr-service"
VERSION="v1.2"
FULL_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}:${VERSION}"
NAMESPACE="dev"
DEPLOYMENT_NAME="asr-service"

echo "=========================================="
echo "ASR Service - Build and Deploy"
echo "=========================================="
echo ""

# Step 1: Navigate to service directory
echo "Step 1: Navigating to service directory..."
cd "${SERVICE_DIR}" || exit 1
echo "✓ Current directory: $(pwd)"
echo ""

# Step 2: Verify code changes
echo "Step 2: Verifying code changes..."
if grep -q 'redis_password = os.getenv("REDIS_PASSWORD", "")' main.py; then
    echo "✓ Redis password defaults to empty string"
else
    echo "✗ ERROR: Code changes not found. Please verify main.py has been updated."
    exit 1
fi

if grep -q 'if redis_password:' main.py; then
    echo "✓ Password is conditionally passed"
else
    echo "✗ ERROR: Password conditional check not found."
    exit 1
fi

if ! grep -n "redis_client.ping()" main.py | grep -v "await redis_client.ping()" | grep -v "#"; then
    echo "✓ No un-awaited ping() calls at module level"
else
    echo "⚠ WARNING: Found un-awaited ping() calls. Please check main.py"
fi
echo ""

# Step 3: Login to AWS ECR
echo "Step 3: Logging in to AWS ECR..."
if aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com; then
    echo "✓ Successfully logged in to ECR"
else
    echo "✗ ERROR: Failed to login to ECR. Check AWS credentials."
    exit 1
fi
echo ""

# Step 4: Build Docker image
echo "Step 4: Building Docker image..."
echo "Image: ${FULL_IMAGE}"
if docker build -t ${FULL_IMAGE} .; then
    echo "✓ Docker image built successfully"
else
    echo "✗ ERROR: Docker build failed"
    exit 1
fi
echo ""

# Step 5: Push to ECR
echo "Step 5: Pushing image to ECR..."
if docker push ${FULL_IMAGE}; then
    echo "✓ Image pushed successfully"
else
    echo "✗ ERROR: Failed to push image"
    exit 1
fi
echo ""

# Step 6: Update Kubernetes deployment
echo "Step 6: Updating Kubernetes deployment..."
if kubectl set image deployment/${DEPLOYMENT_NAME} \
    ${DEPLOYMENT_NAME}=${FULL_IMAGE} \
    -n ${NAMESPACE}; then
    echo "✓ Deployment updated"
else
    echo "✗ ERROR: Failed to update deployment"
    exit 1
fi
echo ""

# Step 7: Wait for rollout
echo "Step 7: Waiting for deployment rollout..."
if kubectl rollout status deployment/${DEPLOYMENT_NAME} -n ${NAMESPACE} --timeout=300s; then
    echo "✓ Deployment rolled out successfully"
else
    echo "✗ ERROR: Deployment rollout failed or timed out"
    exit 1
fi
echo ""

# Step 8: Verify deployment
echo "Step 8: Verifying deployment..."
POD_NAME=$(kubectl get pods -n ${NAMESPACE} -l app=${DEPLOYMENT_NAME} -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "${POD_NAME}" ]; then
    echo "⚠ WARNING: Could not find pod name"
else
    echo "Pod name: ${POD_NAME}"
    echo ""
    echo "Checking logs for errors..."
    echo "--- Recent logs ---"
    kubectl logs ${POD_NAME} -n ${NAMESPACE} --tail=50 | grep -E "(Redis|ping|AUTH|ERROR|WARNING)" || echo "No Redis-related errors found"
    echo ""
fi

echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check logs: kubectl logs ${POD_NAME} -n ${NAMESPACE}"
echo "2. Test health: kubectl port-forward deployment/${DEPLOYMENT_NAME} 8087:8087 -n ${NAMESPACE}"
echo "3. Then in another terminal: curl http://localhost:8087/health"
echo ""






















