#!/bin/bash

# AI Model Deployment Test Script
# This script tests the deployed AI model endpoints and functionality

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Test configuration
API_KEY="triton-asr-api-key-2024"
TIMEOUT=30

# Get cluster information
get_cluster_info() {
    print_status "Getting cluster information..."
    
    # Get node IP
    NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
    if [ -z "$NODE_IP" ]; then
        NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
    fi
    
    # Get Kong service IP
    KONG_IP=$(kubectl get svc -n kong kong-service -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    
    print_status "Node IP: $NODE_IP"
    print_status "Kong IP: ${KONG_IP:-"Not available"}"
}

# Test pod status
test_pod_status() {
    print_status "Testing pod status..."
    
    # Check if pods are running
    RUNNING_PODS=$(kubectl get pods -l app=triton-multilingual-asr --field-selector=status.phase=Running --no-headers | wc -l)
    
    if [ "$RUNNING_PODS" -gt 0 ]; then
        print_success "Found $RUNNING_PODS running pod(s)"
        
        # Show pod details
        kubectl get pods -l app=triton-multilingual-asr
    else
        print_error "No running pods found"
        return 1
    fi
}

# Test service endpoints
test_service_endpoints() {
    print_status "Testing service endpoints..."
    
    # Test HTTP endpoint
    if curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30080/v2/health/ready > /dev/null; then
        print_success "HTTP endpoint (port 30080) is accessible"
    else
        print_error "HTTP endpoint (port 30080) is not accessible"
        return 1
    fi
    
    # Test gRPC endpoint (basic connectivity)
    if timeout 5 bash -c "echo > /dev/tcp/$NODE_IP/30081"; then
        print_success "gRPC endpoint (port 30081) is accessible"
    else
        print_error "gRPC endpoint (port 30081) is not accessible"
        return 1
    fi
    
    # Test metrics endpoint
    if curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30082/metrics > /dev/null; then
        print_success "Metrics endpoint (port 30082) is accessible"
    else
        print_error "Metrics endpoint (port 30082) is not accessible"
        return 1
    fi
}

# Test health endpoints
test_health_endpoints() {
    print_status "Testing health endpoints..."
    
    # Test liveness endpoint
    if curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30080/v2/health/live | grep -q "OK"; then
        print_success "Liveness endpoint is healthy"
    else
        print_error "Liveness endpoint is not healthy"
        return 1
    fi
    
    # Test readiness endpoint
    if curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30080/v2/health/ready | grep -q "OK"; then
        print_success "Readiness endpoint is healthy"
    else
        print_error "Readiness endpoint is not healthy"
        return 1
    fi
}

# Test models endpoint
test_models_endpoint() {
    print_status "Testing models endpoint..."
    
    # Test models endpoint
    MODELS_RESPONSE=$(curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30080/v2/models)
    
    if [ $? -eq 0 ] && [ -n "$MODELS_RESPONSE" ]; then
        print_success "Models endpoint is accessible"
        print_status "Models response: $MODELS_RESPONSE"
    else
        print_error "Models endpoint is not accessible"
        return 1
    fi
}

# Test Kong integration
test_kong_integration() {
    if [ -z "$KONG_IP" ]; then
        print_warning "Kong service not found, skipping Kong tests"
        return 0
    fi
    
    print_status "Testing Kong integration..."
    
    # Test Kong health
    if curl -s --connect-timeout $TIMEOUT http://$KONG_IP:8000/status > /dev/null; then
        print_success "Kong service is accessible"
    else
        print_error "Kong service is not accessible"
        return 1
    fi
    
    # Test ASR endpoint through Kong
    if curl -s --connect-timeout $TIMEOUT \
        -H "X-API-Key: $API_KEY" \
        http://$KONG_IP:8000/api/v1/asr > /dev/null; then
        print_success "ASR endpoint through Kong is accessible"
    else
        print_error "ASR endpoint through Kong is not accessible"
        return 1
    fi
}

# Test GPU usage
test_gpu_usage() {
    print_status "Testing GPU usage..."
    
    # Get pod name
    POD_NAME=$(kubectl get pods -l app=triton-multilingual-asr --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
    
    if [ -n "$POD_NAME" ]; then
        # Check if nvidia-smi is available
        if kubectl exec $POD_NAME -- nvidia-smi > /dev/null 2>&1; then
            print_success "GPU is accessible in pod"
            
            # Show GPU status
            print_status "GPU Status:"
            kubectl exec $POD_NAME -- nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
        else
            print_error "GPU is not accessible in pod"
            return 1
        fi
    else
        print_error "No running pod found for GPU test"
        return 1
    fi
}

# Test resource usage
test_resource_usage() {
    print_status "Testing resource usage..."
    
    # Check CPU and memory usage
    kubectl top pods -l app=triton-multilingual-asr
    
    # Check resource limits
    print_status "Resource limits:"
    kubectl describe pod -l app=triton-multilingual-asr | grep -A 10 "Limits:"
}

# Test HPA
test_hpa() {
    print_status "Testing Horizontal Pod Autoscaler..."
    
    # Check HPA status
    HPA_STATUS=$(kubectl get hpa triton-multilingual-asr-hpa -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || echo "NotFound")
    
    if [ "$HPA_STATUS" = "True" ]; then
        print_success "HPA is active"
        kubectl get hpa triton-multilingual-asr-hpa
    else
        print_warning "HPA is not active or not found"
    fi
}

# Test PDB
test_pdb() {
    print_status "Testing Pod Disruption Budget..."
    
    # Check PDB status
    if kubectl get pdb triton-multilingual-asr-pdb > /dev/null 2>&1; then
        print_success "PDB is configured"
        kubectl get pdb triton-multilingual-asr-pdb
    else
        print_warning "PDB is not configured"
    fi
}

# Performance test
test_performance() {
    print_status "Running performance test..."
    
    # Test response time
    START_TIME=$(date +%s%N)
    curl -s --connect-timeout $TIMEOUT http://$NODE_IP:30080/v2/health/ready > /dev/null
    END_TIME=$(date +%s%N)
    
    RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))
    
    if [ $RESPONSE_TIME -lt 1000 ]; then
        print_success "Response time: ${RESPONSE_TIME}ms (excellent)"
    elif [ $RESPONSE_TIME -lt 3000 ]; then
        print_success "Response time: ${RESPONSE_TIME}ms (good)"
    else
        print_warning "Response time: ${RESPONSE_TIME}ms (slow)"
    fi
}

# Generate test report
generate_report() {
    print_status "Generating test report..."
    
    REPORT_FILE="test-report-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "AI Model Deployment Test Report"
        echo "=============================="
        echo "Date: $(date)"
        echo "Node IP: $NODE_IP"
        echo "Kong IP: ${KONG_IP:-"Not available"}"
        echo ""
        echo "Pod Status:"
        kubectl get pods -l app=triton-multilingual-asr
        echo ""
        echo "Service Status:"
        kubectl get svc -l app=triton-multilingual-asr
        echo ""
        echo "HPA Status:"
        kubectl get hpa triton-multilingual-asr-hpa 2>/dev/null || echo "HPA not found"
        echo ""
        echo "PDB Status:"
        kubectl get pdb triton-multilingual-asr-pdb 2>/dev/null || echo "PDB not found"
    } > $REPORT_FILE
    
    print_success "Test report saved to: $REPORT_FILE"
}

# Main test function
run_tests() {
    print_status "Starting AI Model deployment tests..."
    echo "=========================================="
    
    # Get cluster info
    get_cluster_info
    
    # Run tests
    test_pod_status || exit 1
    test_service_endpoints || exit 1
    test_health_endpoints || exit 1
    test_models_endpoint || exit 1
    test_kong_integration || print_warning "Kong integration test failed"
    test_gpu_usage || print_warning "GPU test failed"
    test_resource_usage
    test_hpa
    test_pdb
    test_performance
    
    # Generate report
    generate_report
    
    print_success "All tests completed!"
}

# Handle command line arguments
case "${1:-}" in
    "quick")
        print_status "Running quick tests..."
        get_cluster_info
        test_pod_status
        test_health_endpoints
        ;;
    "full")
        run_tests
        ;;
    "gpu")
        print_status "Testing GPU functionality..."
        get_cluster_info
        test_gpu_usage
        ;;
    "kong")
        print_status "Testing Kong integration..."
        get_cluster_info
        test_kong_integration
        ;;
    *)
        run_tests
        ;;
esac


