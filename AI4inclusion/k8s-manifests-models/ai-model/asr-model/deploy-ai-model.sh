#!/bin/bash

# AI Model Deployment Script for Triton Multilingual ASR
# This script deploys the AI model on GPU nodes with proper configuration

set -e

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
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    print_success "kubectl is available"
}

# Check if cluster is accessible
check_cluster() {
    print_status "Checking cluster connectivity..."
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    print_success "Cluster is accessible"
}

# Check for GPU nodes
check_gpu_nodes() {
    print_status "Checking for GPU nodes..."
    gpu_nodes=$(kubectl get nodes -l node-type=gpu --no-headers | wc -l)
    if [ "$gpu_nodes" -eq 0 ]; then
        print_warning "No GPU nodes found with label 'node-type=gpu'"
        print_status "Available nodes:"
        kubectl get nodes
        print_warning "Please ensure GPU nodes are labeled with 'node-type=gpu'"
    else
        print_success "Found $gpu_nodes GPU node(s)"
    fi
}

# Check for NVIDIA GPU operator
check_nvidia_gpu_operator() {
    print_status "Checking for NVIDIA GPU operator..."
    if kubectl get pods -n gpu-operator --no-headers | grep -q nvidia-operator; then
        print_success "NVIDIA GPU operator is running"
    else
        print_warning "NVIDIA GPU operator not found. GPU support may not be available."
        print_status "Please install NVIDIA GPU operator for proper GPU support"
    fi
}

# Deploy AI model
deploy_ai_model() {
    print_status "Deploying AI model manifests..."
    
    # Apply deployment
    print_status "Applying AI model deployment..."
    kubectl apply -f ai-model-deployment.yaml
    
    # Apply service
    print_status "Applying AI model service..."
    kubectl apply -f ai-model-service.yaml
    
    # Apply HPA
    print_status "Applying Horizontal Pod Autoscaler..."
    kubectl apply -f ai-model-hpa.yaml
    
    # Apply PDB
    print_status "Applying Pod Disruption Budget..."
    kubectl apply -f ai-model-pdb.yaml
    
    print_success "AI model manifests applied successfully"
}

# Wait for deployment to be ready
wait_for_deployment() {
    print_status "Waiting for AI model deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/triton-multilingual-asr
    print_success "AI model deployment is ready"
}

# Update Kong configuration
update_kong_config() {
    print_status "Updating Kong configuration..."
    
    # Check if Kong is running
    if kubectl get pods -n kong | grep -q kong; then
        print_status "Kong is running, updating configuration..."
        kubectl apply -f ../kong-api-gateway/kong-config.yaml
        
        # Restart Kong to apply new configuration
        print_status "Restarting Kong to apply new configuration..."
        kubectl rollout restart deployment/kong -n kong
        kubectl wait --for=condition=available --timeout=120s deployment/kong -n kong
        
        print_success "Kong configuration updated successfully"
    else
        print_warning "Kong is not running. Please deploy Kong first."
    fi
}

# Show deployment status
show_status() {
    print_status "Deployment Status:"
    echo "===================="
    
    print_status "AI Model Pods:"
    kubectl get pods -l app=triton-multilingual-asr
    
    print_status "AI Model Services:"
    kubectl get svc -l app=triton-multilingual-asr
    
    print_status "HPA Status:"
    kubectl get hpa triton-multilingual-asr-hpa
    
    print_status "Pod Disruption Budget:"
    kubectl get pdb triton-multilingual-asr-pdb
    
    print_status "Kong Services:"
    kubectl get svc -n kong
}

# Show access information
show_access_info() {
    print_status "Access Information:"
    echo "===================="
    
    # Get service information
    NODE_PORT_HTTP=$(kubectl get svc triton-multilingual-asr-nodeport -o jsonpath='{.spec.ports[0].nodePort}')
    NODE_PORT_GRPC=$(kubectl get svc triton-multilingual-asr-nodeport -o jsonpath='{.spec.ports[1].nodePort}')
    NODE_PORT_METRICS=$(kubectl get svc triton-multilingual-asr-nodeport -o jsonpath='{.spec.ports[2].nodePort}')
    
    # Get node IP
    NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
    if [ -z "$NODE_IP" ]; then
        NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    fi
    
    echo "Direct Access (NodePort):"
    echo "  HTTP API: http://$NODE_IP:$NODE_PORT_HTTP"
    echo "  gRPC API: $NODE_IP:$NODE_PORT_GRPC"
    echo "  Metrics:  http://$NODE_IP:$NODE_PORT_METRICS"
    echo ""
    echo "Kong Gateway Access:"
    echo "  ASR API: https://your-domain.com/api/v1/asr"
    echo "  Models:  https://your-domain.com/v2/models"
    echo "  Health:  https://your-domain.com/v2/health"
    echo ""
    echo "API Key: triton-asr-api-key-2024"
}

# Cleanup function
cleanup() {
    print_status "Cleaning up AI model deployment..."
    kubectl delete -f ai-model-deployment.yaml --ignore-not-found=true
    kubectl delete -f ai-model-service.yaml --ignore-not-found=true
    kubectl delete -f ai-model-hpa.yaml --ignore-not-found=true
    kubectl delete -f ai-model-pdb.yaml --ignore-not-found=true
    print_success "Cleanup completed"
}

# Main execution
main() {
    print_status "Starting AI Model Deployment..."
    echo "====================================="
    
    # Pre-deployment checks
    check_kubectl
    check_cluster
    check_gpu_nodes
    check_nvidia_gpu_operator
    
    # Deploy AI model
    deploy_ai_model
    wait_for_deployment
    
    # Update Kong configuration
    update_kong_config
    
    # Show status and access information
    show_status
    show_access_info
    
    print_success "AI Model deployment completed successfully!"
}

# Handle command line arguments
case "${1:-}" in
    "cleanup")
        cleanup
        ;;
    "status")
        show_status
        ;;
    "access")
        show_access_info
        ;;
    *)
        main
        ;;
esac


