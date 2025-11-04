#!/bin/bash

# AI4Inclusion Kubernetes Deployment Script
# This script deploys all microservices to the dev namespace

set -e

echo "🚀 Starting AI4Inclusion Kubernetes Deployment..."

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

# Create namespace
echo "📦 Creating dev namespace..."
kubectl apply -f namespace.yaml

# Deploy infrastructure services
echo "🏗️  Deploying infrastructure services..."

echo "  🐘 Deploying PostgreSQL..."
cd services/postgres && ./deploy.sh && cd ../..

echo "  🔴 Deploying Redis..."
cd services/redis && ./deploy.sh && cd ../..

echo "  📈 Deploying InfluxDB..."
cd services/influxdb && ./deploy.sh && cd ../..

echo "  🔍 Deploying Elasticsearch..."
cd services/elasticsearch && ./deploy.sh && cd ../..

echo "  🐘 Deploying Zookeeper..."
cd services/zookeeper && ./deploy.sh && cd ../..

echo "  📨 Deploying Kafka..."
cd services/kafka && ./deploy.sh && cd ../..

# Deploy microservices
echo "🔧 Deploying microservices..."

echo "  🌐 Deploying API Gateway..."
cd services/api-gateway-service && ./deploy.sh && cd ../..

echo "  🔐 Deploying Auth Service..."
cd services/auth-service && ./deploy.sh && cd ../..

echo "  ⚙️  Deploying Config Service..."
cd services/config-service && ./deploy.sh && cd ../..

echo "  📊 Deploying Metrics Service..."
cd services/metrics-service && ./deploy.sh && cd ../..

echo "  📡 Deploying Telemetry Service..."
cd services/telemetry-service && ./deploy.sh && cd ../..

echo "  🚨 Deploying Alerting Service..."
cd services/alerting-service && ./deploy.sh && cd ../..

echo "  📊 Deploying Dashboard Service..."
cd services/dashboard-service && ./deploy.sh && cd ../..

echo "  🎤 Deploying ASR Service..."
cd services/asr-service && ./deploy.sh && cd ../..

echo "  🔊 Deploying TTS Service..."
cd services/tts-service && ./deploy.sh && cd ../..

echo "  🌍 Deploying NMT Service..."
cd services/nmt-service && ./deploy.sh && cd ../..

echo "  🔄 Deploying Pipeline Service..."
cd services/pipeline-service && ./deploy.sh && cd ../..

# Deploy Frontend
echo "  🎨 Deploying Frontend..."
cd services/simple-ui-frontend && ./deploy.sh && cd ../..

echo "✅ All services deployed successfully!"

# Display service status
echo "📋 Service Status:"
kubectl get pods -n dev
echo ""
echo "🌐 Services:"
kubectl get services -n dev

echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "To access the services:"
echo "  - Frontend: kubectl port-forward service/simple-ui-frontend 3000:3000 -n dev"
echo "  - API Gateway: kubectl port-forward service/api-gateway-service 8080:8080 -n dev"
echo "  - Dashboard: kubectl port-forward service/dashboard-service 8501:8501 -n dev"
echo ""
echo "To check logs:"
echo "  - kubectl logs -f deployment/api-gateway-service -n dev"
echo "  - kubectl logs -f deployment/auth-service -n dev"
echo "  - etc."