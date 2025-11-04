#!/bin/bash

# AI4Voice-core Simplified Kubernetes Deployment Script
# This script deploys Nginx Ingress + Kong API Gateway + Sample Services

set -e

echo "🚀 Starting AI4Voice-core Simplified Kubernetes deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed or not in PATH"
    exit 1
fi

# Check if we can connect to the cluster
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

print_success "Connected to Kubernetes cluster"

# Step 1: Deploy Nginx Ingress Controller
print_status "Deploying Nginx Ingress Controller..."
kubectl apply -f nginx-ingress/nginx-ingress-controller.yaml
kubectl wait --for=condition=available --timeout=300s deployment/nginx-ingress-controller -n ingress-nginx
print_success "Nginx Ingress Controller deployed"

# Step 2: Deploy Kong API Gateway
print_status "Deploying Kong API Gateway..."
kubectl apply -f kong-api-gateway/kong-namespace.yaml
kubectl apply -f kong-api-gateway/kong-config.yaml
kubectl apply -f kong-api-gateway/kong-deployment.yaml
kubectl wait --for=condition=available --timeout=300s deployment/kong-gateway -n kong
print_success "Kong API Gateway deployed"

# Step 3: Deploy sample services
print_status "Deploying sample services..."
kubectl apply -f services/ai-model-service.yaml
kubectl apply -f services/dhruva-service.yaml
kubectl wait --for=condition=available --timeout=300s deployment/ai-model-service
kubectl wait --for=condition=available --timeout=300s deployment/dhruva-service
print_success "Sample services deployed"

# Step 4: Deploy Kong Ingress
print_status "Deploying Kong Ingress..."
kubectl apply -f kong-api-gateway/kong-ingress.yaml
print_success "Kong Ingress deployed"

# Display deployment status
print_status "Deployment completed! Here's the status:"

echo ""
echo "📊 Deployment Status:"
echo "===================="

# Show pods
echo "Pods:"
kubectl get pods -A | grep -E "(kong|nginx|ai-model|dhruva)"

echo ""
echo "Services:"
kubectl get services -A | grep -E "(kong|nginx|ai-model|dhruva)"

echo ""
echo "Ingress:"
kubectl get ingress -A

echo ""
echo "LoadBalancer Services:"
kubectl get services -A --field-selector spec.type=LoadBalancer

echo ""
print_success "🎉 AI4Voice-core simplified deployment completed successfully!"
print_status "Next steps:"
echo "1. Get the NLB external IP:"
echo "   kubectl get service ingress-nginx -n ingress-nginx"
echo ""
echo "2. Configure your domain DNS to point to the NLB IP:"
echo "   dev.ai4inclusion.org    A    <NLB_IP>"
echo ""
echo "3. Test your services:"
echo "   curl -H \"apikey: ai4voice-api-key-2024\" http://<NLB_IP>/api/v1/ai-models"
echo "   curl -H \"apikey: dhruva-api-key-2024\" http://<NLB_IP>/api/v1/dhruva"
echo ""
echo "4. Access services via Ingress:"
echo "   https://dev.ai4inclusion.org (after DNS setup)"
