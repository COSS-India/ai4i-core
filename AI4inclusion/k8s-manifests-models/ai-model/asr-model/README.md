# AI Model Deployment - Triton Multilingual ASR

This directory contains Kubernetes manifests and deployment scripts for the AI4Bharat Triton Multilingual ASR model on GPU-enabled Kubernetes clusters.

## Overview

The Triton Multilingual ASR (Automatic Speech Recognition) model is deployed using:
- **Image**: `ai4bharat/triton-multilingual-asr:latest`
- **GPU Support**: NVIDIA GPU acceleration
- **API**: HTTP, gRPC, and Metrics endpoints
- **Gateway**: Kong API Gateway integration
- **Scaling**: Horizontal Pod Autoscaler (HPA)
- **High Availability**: Pod Disruption Budget (PDB)

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kong Gateway  │────│  AI Model Pod   │────│   GPU Node      │
│                 │    │  (Triton ASR)   │    │                 │
│ - Rate Limiting │    │ - HTTP: 8000    │    │ - NVIDIA GPU    │
│ - Authentication│    │ - gRPC: 8001    │    │ - CUDA Runtime  │
│ - CORS          │    │ - Metrics: 8002 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Prerequisites

### 1. Kubernetes Cluster with GPU Support
- Kubernetes cluster with GPU nodes
- NVIDIA GPU Operator installed
- GPU nodes labeled with `node-type=gpu`

### 2. Required Tools
- `kubectl` configured to access your cluster
- `curl` for testing endpoints

### 3. GPU Node Setup
Ensure your GPU nodes have the following labels:
```bash
kubectl label nodes <gpu-node-name> node-type=gpu
```

## Files Description

| File | Description |
|------|-------------|
| `ai-model-deployment.yaml` | Main deployment manifest with GPU support |
| `ai-model-service.yaml` | ClusterIP and NodePort services |
| `ai-model-hpa.yaml` | Horizontal Pod Autoscaler configuration |
| `ai-model-pdb.yaml` | Pod Disruption Budget for high availability |
| `deploy-ai-model.sh` | Automated deployment script |
| `README.md` | This documentation file |

## Quick Start

### 1. Deploy the AI Model
```bash
cd k8s-manifests-simplified/ai-model
./deploy-ai-model.sh
```

### 2. Check Deployment Status
```bash
./deploy-ai-model.sh status
```

### 3. Get Access Information
```bash
./deploy-ai-model.sh access
```

## Manual Deployment

If you prefer to deploy manually:

```bash
# Apply all manifests
kubectl apply -f ai-model-deployment.yaml
kubectl apply -f ai-model-service.yaml
kubectl apply -f ai-model-hpa.yaml
kubectl apply -f ai-model-pdb.yaml

# Update Kong configuration
kubectl apply -f ../kong-api-gateway/kong-config.yaml
kubectl rollout restart deployment/kong -n kong
```

## Configuration Details

### Resource Allocation
- **GPU**: 1 NVIDIA GPU per pod
- **CPU**: 2-4 cores per pod
- **Memory**: 8-16 GB per pod
- **Replicas**: 1-5 pods (auto-scaling)

### Ports
- **8000**: HTTP API (Triton server)
- **8001**: gRPC API
- **8002**: Metrics endpoint

### Environment Variables
- `CUDA_VISIBLE_DEVICES=0`: GPU device selection
- `TRITON_SERVER_HTTP_PORT=8000`: HTTP port
- `TRITON_SERVER_GRPC_PORT=8001`: gRPC port
- `TRITON_SERVER_METRICS_PORT=8002`: Metrics port

## API Endpoints

### Direct Access (NodePort)
- **HTTP API**: `http://<node-ip>:30080`
- **gRPC API**: `<node-ip>:30081`
- **Metrics**: `http://<node-ip>:30082`

### Kong Gateway Access
- **ASR API**: `https://your-domain.com/api/v1/asr`
- **Models**: `https://your-domain.com/v2/models`
- **Health**: `https://your-domain.com/v2/health`

### Authentication
All requests through Kong require an API key:
```
X-API-Key: triton-asr-api-key-2024
```

## Testing the Deployment

### 1. Health Check
```bash
# Direct access
curl http://<node-ip>:30080/v2/health/ready

# Through Kong (if configured)
curl -H "X-API-Key: triton-asr-api-key-2024" \
     https://your-domain.com/v2/health/ready
```

### 2. List Models
```bash
# Direct access
curl http://<node-ip>:30080/v2/models

# Through Kong
curl -H "X-API-Key: triton-asr-api-key-2024" \
     https://your-domain.com/v2/models
```

### 3. ASR Inference
```bash
# Example ASR request
curl -X POST \
     -H "Content-Type: application/json" \
     -H "X-API-Key: triton-asr-api-key-2024" \
     -d '{"audio": "base64-encoded-audio"}' \
     https://your-domain.com/api/v1/asr/infer
```

## Monitoring and Troubleshooting

### Check Pod Status
```bash
kubectl get pods -l app=triton-multilingual-asr
kubectl describe pod <pod-name>
```

### Check GPU Usage
```bash
kubectl exec -it <pod-name> -- nvidia-smi
```

### View Logs
```bash
kubectl logs -l app=triton-multilingual-asr
kubectl logs -l app=triton-multilingual-asr --previous
```

### Check HPA Status
```bash
kubectl get hpa triton-multilingual-asr-hpa
kubectl describe hpa triton-multilingual-asr-hpa
```

### Check Kong Integration
```bash
kubectl get svc -n kong
kubectl logs -l app=kong -n kong
```

## Scaling Configuration

### Horizontal Pod Autoscaler
- **Min Replicas**: 1
- **Max Replicas**: 5
- **CPU Target**: 70%
- **Memory Target**: 80%

### Scaling Policies
- **Scale Up**: 50% increase or 2 pods per minute
- **Scale Down**: 10% decrease per minute
- **Stabilization**: 5 minutes for scale down, 1 minute for scale up

## Security Considerations

### API Key Management
- Rotate API keys regularly
- Use different keys for different environments
- Monitor API key usage

### Network Security
- Use TLS/SSL for production
- Configure proper firewall rules
- Implement network policies

### Resource Limits
- Set appropriate CPU and memory limits
- Monitor GPU usage
- Implement resource quotas

## Cleanup

To remove the AI model deployment:

```bash
# Using the script
./deploy-ai-model.sh cleanup

# Or manually
kubectl delete -f ai-model-deployment.yaml
kubectl delete -f ai-model-service.yaml
kubectl delete -f ai-model-hpa.yaml
kubectl delete -f ai-model-pdb.yaml
```

## Troubleshooting Common Issues

### 1. Pod Stuck in Pending
- Check if GPU nodes are available
- Verify node labels (`node-type=gpu`)
- Check resource availability

### 2. GPU Not Available
- Ensure NVIDIA GPU operator is installed
- Check GPU node configuration
- Verify CUDA runtime

### 3. Kong Integration Issues
- Check Kong service status
- Verify Kong configuration
- Check API key configuration

### 4. High Memory Usage
- Adjust memory limits in deployment
- Check for memory leaks
- Monitor model size

## Support

For issues and questions:
1. Check the logs using the commands above
2. Verify all prerequisites are met
3. Check the Kong configuration
4. Review the resource allocation

## Version History

- **v1.0**: Initial deployment with basic GPU support
- **v1.1**: Added Kong integration and HPA
- **v1.2**: Enhanced monitoring and security features


