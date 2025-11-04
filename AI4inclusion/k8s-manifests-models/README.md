# AI4Voice-core Simplified Kubernetes Deployment

This directory contains a **simplified** Kubernetes deployment setup for the AI4Voice-core project using **Nginx Ingress + Kong API Gateway** (without ALB).

## 🏗️ Simplified Architecture

```
Internet → NLB (Public Subnet) → Nginx Ingress → Kong API Gateway → Services
                                    ↓
                              AI Model Service (GPU)
                              Dhruva Service (CPU)
```

## 📁 Directory Structure

```
k8s-manifests-simplified/
├── nginx-ingress/
│   └── nginx-ingress-controller.yaml  # Nginx Ingress Controller + NLB
├── kong-api-gateway/
│   ├── kong-namespace.yaml           # Kong namespace
│   ├── kong-config.yaml             # Kong configuration & API keys
│   ├── kong-deployment.yaml         # Kong deployment & services
│   └── kong-ingress.yaml            # Kong ingress configuration
├── services/
│   ├── ai-model-service.yaml        # AI Model service (GPU nodes)
│   └── dhruva-service.yaml          # Dhruva service (CPU nodes)
├── deploy.sh                        # Simplified deployment script
└── README.md                        # This file
```

## 🚀 Quick Deployment

### Prerequisites

1. **Kubernetes cluster** (EKS) with kubectl configured
2. **Domain DNS** access for dev.ai4inclusion.org

### Step 1: Deploy Everything

```bash
# Make the script executable
chmod +x deploy.sh

# Run the deployment script
./deploy.sh
```

### Step 2: Get NLB External IP

```bash
kubectl get service ingress-nginx -n ingress-nginx
```

### Step 3: Configure DNS

Point your domain to the NLB IP:

```
dev.ai4inclusion.org    A    <NLB_IP>
```

## 🔧 Manual Deployment Steps

If you prefer to deploy manually:

### 1. Deploy Nginx Ingress Controller

```bash
kubectl apply -f nginx-ingress/nginx-ingress-controller.yaml
kubectl wait --for=condition=available --timeout=300s deployment/nginx-ingress-controller -n ingress-nginx
```

### 2. Deploy Kong API Gateway

```bash
kubectl apply -f kong-api-gateway/kong-namespace.yaml
kubectl apply -f kong-api-gateway/kong-config.yaml
kubectl apply -f kong-api-gateway/kong-deployment.yaml
kubectl wait --for=condition=available --timeout=300s deployment/kong-gateway -n kong
```

### 3. Deploy Sample Services

```bash
kubectl apply -f services/ai-model-service.yaml
kubectl apply -f services/dhruva-service.yaml
kubectl wait --for=condition=available --timeout=300s deployment/ai-model-service
kubectl wait --for=condition=available --timeout=300s deployment/dhruva-service
```

### 4. Deploy Kong Ingress

```bash
kubectl apply -f kong-api-gateway/kong-ingress.yaml
```

## 🌐 Domain Configuration

### DNS Records

Configure your domain DNS records to point to the NLB IP:

```
dev.ai4inclusion.org    A    <NLB_IP>
```

### SSL Certificate (Optional)

For HTTPS, you can add SSL certificates to Nginx:

```yaml
# Add to nginx-ingress-controller.yaml
apiVersion: v1
kind: Secret
metadata:
  name: tls-secret
  namespace: ingress-nginx
type: kubernetes.io/tls
data:
  tls.crt: <base64-encoded-cert>
  tls.key: <base64-encoded-key>
```

## 🔐 API Configuration

### Default API Keys

- **AI Model Service**: `ai4voice-api-key-2024`
- **Dhruva Service**: `dhruva-api-key-2024`

### API Endpoints

- **AI Models**: `http://dev.ai4inclusion.org/api/v1/ai-models`
- **Dhruva**: `http://dev.ai4inclusion.org/api/v1/dhruva`

## 🔍 Verification

### Check Deployment Status

```bash
# Check all pods
kubectl get pods -A

# Check services
kubectl get services -A

# Check ingress
kubectl get ingress -A

# Check NLB
kubectl get service ingress-nginx -n ingress-nginx
```

### Test Services

```bash
# Get NLB IP
NLB_IP=$(kubectl get service ingress-nginx -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test AI Model Service
curl -H "apikey: ai4voice-api-key-2024" http://$NLB_IP/api/v1/ai-models

# Test Dhruva Service
curl -H "apikey: dhruva-api-key-2024" http://$NLB_IP/api/v1/dhruva

# Test Kong Admin
curl http://$NLB_IP:8002
```

## 🎯 Key Features

✅ **AWS Network Load Balancer** (NLB) in public subnets  
✅ **Nginx Ingress Controller** for advanced routing  
✅ **Kong API Gateway** with authentication & rate limiting  
✅ **GPU-based AI Model Service**  
✅ **CPU-based Dhruva Service**  
✅ **Domain configuration** for dev.ai4inclusion.org  
✅ **Simplified deployment** (no ALB complexity)  
✅ **Lower cost** than ALB setup  

## 🔄 Architecture Benefits

### **Simplified Setup:**
- ❌ **No ALB Controller** needed
- ❌ **No SSL certificate ARN** configuration
- ❌ **No AWS-specific annotations**
- ✅ **Just Nginx + Kong + Services**

### **Traffic Flow:**
```
Internet → NLB (AWS) → Nginx Ingress (K8s) → Kong API Gateway → Services
```

### **Cost Comparison:**
- **ALB Setup**: ~$25-50/month
- **NLB Setup**: ~$15-25/month
- **Savings**: ~40-50% lower cost

## 🛠️ Troubleshooting

### Common Issues

1. **NLB not getting external IP**: Check AWS Load Balancer Controller permissions
2. **Services not responding**: Verify service endpoints and health checks
3. **Kong not accessible**: Check ingress configuration and DNS
4. **SSL issues**: Verify certificate configuration

### Debug Commands

```bash
# Check Nginx Ingress logs
kubectl logs -n ingress-nginx deployment/nginx-ingress-controller

# Check Kong logs
kubectl logs -n kong deployment/kong-gateway

# Check service endpoints
kubectl get endpoints

# Check NLB status
kubectl describe service ingress-nginx -n ingress-nginx
```

## 📝 Notes

- **GPU nodes** are required for AI Model Service
- **CPU nodes** are used for Dhruva Service
- **System nodes** handle CoreDNS and other system pods
- **Bastion host** provides secure access to the cluster
- **Domain**: dev.ai4inclusion.org
- **Region**: ap-south-1
- **Load Balancer**: AWS Network Load Balancer (NLB)
