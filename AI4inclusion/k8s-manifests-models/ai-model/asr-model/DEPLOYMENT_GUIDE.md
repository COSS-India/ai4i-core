# AI Model Deployment Guide

## Step-by-Step Deployment Instructions

This guide provides detailed instructions for deploying the Triton Multilingual ASR AI model on a GPU-enabled Kubernetes cluster.

## Prerequisites Checklist

### 1. Kubernetes Cluster Requirements
- [ ] Kubernetes cluster (v1.20+)
- [ ] GPU nodes with NVIDIA GPUs
- [ ] NVIDIA GPU Operator installed
- [ ] `kubectl` configured and accessible

### 2. GPU Node Preparation
```bash
# Label GPU nodes
kubectl label nodes <gpu-node-1> node-type=gpu
kubectl label nodes <gpu-node-2> node-type=gpu

# Verify labels
kubectl get nodes -l node-type=gpu
```

### 3. Verify GPU Operator
```bash
# Check if NVIDIA GPU operator is running
kubectl get pods -n gpu-operator

# Check GPU resources
kubectl describe nodes | grep nvidia.com/gpu
```

## Deployment Steps

### Step 1: Clone and Navigate
```bash
git clone <your-repo>
cd AI4inclusion/k8s-manifests-simplified/ai-model
```

### Step 2: Review Configuration
```bash
# Review the deployment configuration
cat ai-model-deployment.yaml

# Check resource requirements
grep -A 10 "resources:" ai-model-deployment.yaml
```

### Step 3: Deploy AI Model
```bash
# Make script executable
chmod +x deploy-ai-model.sh

# Run deployment
./deploy-ai-model.sh
```

### Step 4: Verify Deployment
```bash
# Check pod status
kubectl get pods -l app=triton-multilingual-asr

# Check services
kubectl get svc -l app=triton-multilingual-asr

# Check HPA
kubectl get hpa triton-multilingual-asr-hpa
```

### Step 5: Test Endpoints
```bash
# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')

# Test health endpoint
curl http://$NODE_IP:30080/v2/health/ready

# Test models endpoint
curl http://$NODE_IP:30080/v2/models
```

## Kong Gateway Integration

### Step 1: Deploy Kong (if not already deployed)
```bash
cd ../kong-api-gateway
kubectl apply -f kong-namespace.yaml
kubectl apply -f kong-deployment.yaml
kubectl apply -f kong-ingress.yaml
```

### Step 2: Apply Kong Configuration
```bash
# Apply updated Kong configuration
kubectl apply -f kong-config.yaml

# Restart Kong to apply changes
kubectl rollout restart deployment/kong -n kong
```

### Step 3: Test Kong Integration
```bash
# Get Kong service IP
KONG_IP=$(kubectl get svc -n kong kong-service -o jsonpath='{.spec.clusterIP}')

# Test through Kong
curl -H "X-API-Key: triton-asr-api-key-2024" \
     http://$KONG_IP:8000/api/v1/asr
```

## Production Configuration

### 1. SSL/TLS Setup
```bash
# Apply SSL certificates
kubectl apply -f ../ssl-certificates/tls-secret.yaml

# Update Kong ingress with SSL
kubectl apply -f ../kong-api-gateway/kong-ingress.yaml
```

### 2. Monitoring Setup
```bash
# Install Prometheus (if not already installed)
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/bundle.yaml

# Install Grafana (if not already installed)
kubectl apply -f https://raw.githubusercontent.com/grafana/helm-charts/main/charts/grafana/templates/deployment.yaml
```

### 3. Logging Setup
```bash
# Install Fluentd or similar logging solution
# Configure log aggregation for AI model pods
```

## Security Hardening

### 1. Network Policies
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: triton-asr-network-policy
spec:
  podSelector:
    matchLabels:
      app: triton-multilingual-asr
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: kong
    ports:
    - protocol: TCP
      port: 8000
    - protocol: TCP
      port: 8001
    - protocol: TCP
      port: 8002
```

### 2. Pod Security Policies
```yaml
apiVersion: policy/v1beta1
kind: PodSecurityPolicy
metadata:
  name: triton-asr-psp
spec:
  privileged: false
  allowPrivilegeEscalation: false
  requiredDropCapabilities:
  - ALL
  volumes:
  - 'configMap'
  - 'emptyDir'
  - 'projected'
  - 'secret'
  - 'downwardAPI'
  - 'persistentVolumeClaim'
  runAsUser:
    rule: 'MustRunAsNonRoot'
  seLinux:
    rule: 'RunAsAny'
  fsGroup:
    rule: 'RunAsAny'
```

## Performance Tuning

### 1. GPU Memory Optimization
```yaml
# Add to deployment spec
env:
- name: CUDA_MEMORY_FRACTION
  value: "0.8"
- name: TRITON_MEMORY_POOL_BYTE_SIZE
  value: "2147483648"  # 2GB
```

### 2. CPU Optimization
```yaml
# Adjust CPU requests/limits based on workload
resources:
  requests:
    cpu: 4000m
    memory: 16Gi
  limits:
    cpu: 8000m
    memory: 32Gi
```

### 3. Network Optimization
```yaml
# Add to service spec
spec:
  type: LoadBalancer
  sessionAffinity: ClientIP
  sessionAffinityConfig:
    clientIP:
      timeoutSeconds: 3600
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Pod Stuck in Pending
```bash
# Check node resources
kubectl describe nodes

# Check pod events
kubectl describe pod <pod-name>

# Check GPU availability
kubectl get nodes -o jsonpath='{.items[*].status.allocatable.nvidia\.com/gpu}'
```

#### 2. GPU Not Detected
```bash
# Check NVIDIA driver
kubectl exec -it <pod-name> -- nvidia-smi

# Check CUDA runtime
kubectl exec -it <pod-name> -- nvcc --version

# Check GPU operator logs
kubectl logs -n gpu-operator -l app=nvidia-operator
```

#### 3. Memory Issues
```bash
# Check memory usage
kubectl top pods -l app=triton-multilingual-asr

# Check memory limits
kubectl describe pod <pod-name> | grep -A 5 "Limits:"

# Adjust memory limits if needed
kubectl edit deployment triton-multilingual-asr
```

#### 4. Kong Integration Issues
```bash
# Check Kong status
kubectl get pods -n kong

# Check Kong logs
kubectl logs -n kong -l app=kong

# Test Kong configuration
kubectl exec -it <kong-pod> -n kong -- kong config db_export
```

## Monitoring and Alerting

### 1. Prometheus Metrics
```yaml
# Add to deployment
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8002"
  prometheus.io/path: "/metrics"
```

### 2. Grafana Dashboard
```json
{
  "dashboard": {
    "title": "Triton ASR Monitoring",
    "panels": [
      {
        "title": "GPU Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "nvidia_gpu_utilization_percent"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "container_memory_usage_bytes{pod=~\"triton-multilingual-asr.*\"}"
          }
        ]
      }
    ]
  }
}
```

### 3. Alerting Rules
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: triton-asr-alerts
spec:
  groups:
  - name: triton-asr
    rules:
    - alert: TritonASRHighMemoryUsage
      expr: container_memory_usage_bytes{pod=~"triton-multilingual-asr.*"} > 0.9 * container_spec_memory_limit_bytes{pod=~"triton-multilingual-asr.*"}
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: "Triton ASR pod memory usage is high"
```

## Backup and Recovery

### 1. Configuration Backup
```bash
# Backup all manifests
kubectl get all -l app=triton-multilingual-asr -o yaml > triton-asr-backup.yaml

# Backup Kong configuration
kubectl get configmap kong-database-config -n kong -o yaml > kong-config-backup.yaml
```

### 2. Model Data Backup
```bash
# If using persistent volumes, backup model data
kubectl exec -it <pod-name> -- tar -czf /tmp/models-backup.tar.gz /models
kubectl cp <pod-name>:/tmp/models-backup.tar.gz ./models-backup.tar.gz
```

## Maintenance

### 1. Regular Updates
```bash
# Update image
kubectl set image deployment/triton-multilingual-asr triton-multilingual-asr=ai4bharat/triton-multilingual-asr:latest

# Rolling update
kubectl rollout status deployment/triton-multilingual-asr
```

### 2. Scaling Operations
```bash
# Scale up
kubectl scale deployment triton-multilingual-asr --replicas=3

# Scale down
kubectl scale deployment triton-multilingual-asr --replicas=1
```

### 3. Cleanup
```bash
# Remove deployment
./deploy-ai-model.sh cleanup

# Remove Kong configuration
kubectl delete configmap kong-database-config -n kong
```

## Support and Documentation

- **Kubernetes Documentation**: https://kubernetes.io/docs/
- **NVIDIA GPU Operator**: https://docs.nvidia.com/datacenter/cloud-native/
- **Triton Inference Server**: https://docs.nvidia.com/deeplearning/triton-inference-server/
- **Kong Gateway**: https://docs.konghq.com/

## Contact

For technical support or questions:
- Create an issue in the repository
- Contact the DevOps team
- Check the troubleshooting section above


