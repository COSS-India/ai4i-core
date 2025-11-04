#!/bin/bash

# SSL Certificate Setup Script for AI4Voice-core
# This script helps you set up SSL certificates for your domain

set -e

echo "🔐 SSL Certificate Setup for AI4Voice-core"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if certificate files exist
if [ ! -f "ai4inclusion.crt" ] || [ ! -f "ai4inclusion.key" ]; then
    print_error "Certificate files not found!"
    echo ""
    echo "Please provide your SSL certificate files:"
    echo "1. ai4inclusion.crt (your certificate file)"
    echo "2. ai4inclusion.key (your private key file)"
    echo ""
    echo "You can obtain certificates from:"
    echo "- Let's Encrypt (free): https://letsencrypt.org/"
    echo "- AWS Certificate Manager (ACM)"
    echo "- Your certificate authority"
    echo ""
    echo "For Let's Encrypt, you can use certbot:"
    echo "sudo certbot certonly --standalone -d dev.ai4inclusion.org"
    exit 1
fi

print_status "Found certificate files. Encoding certificates..."

# Encode certificates to base64
CERT_B64=$(cat ai4inclusion.crt | base64 -w 0)
KEY_B64=$(cat ai4inclusion.key | base64 -w 0)

print_status "Creating TLS secret..."

# Create the TLS secret
cat > tls-secret.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: ai4inclusion-tls-secret
  namespace: ingress-nginx
type: kubernetes.io/tls
data:
  tls.crt: $CERT_B64
  tls.key: $KEY_B64
EOF

print_success "TLS secret created: tls-secret.yaml"

print_status "Applying TLS secret to cluster..."
kubectl apply -f tls-secret.yaml

print_status "Updating Kong ingress with SSL support..."
kubectl apply -f ../kong-api-gateway/kong-ingress.yaml

print_success "SSL configuration completed!"
echo ""
echo "🌐 Your services are now available at:"
echo "   https://dev.ai4inclusion.org"
echo ""
echo "🔍 To verify SSL:"
echo "   curl -I https://dev.ai4inclusion.org"
echo "   openssl s_client -connect dev.ai4inclusion.org:443 -servername dev.ai4inclusion.org"


