# 🔐 SSL Certificate Setup Guide

## Option 1: Let's Encrypt (Free) - Recommended

### Step 1: Install Certbot
```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install certbot

# On Amazon Linux
sudo yum install certbot
```

### Step 2: Get Certificates (dev environment)
```bash
# Stop any web server running on port 80
sudo systemctl stop nginx
sudo systemctl stop apache2

# Get certificate for dev subdomain
sudo certbot certonly --standalone \
  -d dev.ai4inclusion.org

# Certificates will be saved to:
# /etc/letsencrypt/live/dev.ai4inclusion.org/fullchain.pem
# /etc/letsencrypt/live/dev.ai4inclusion.org/privkey.pem
```

### Step 3: Copy Certificates
```bash
# Copy certificates to your working directory (if you still use manual secrets)
sudo cp /etc/letsencrypt/live/dev.ai4inclusion.org/fullchain.pem ./dev.ai4inclusion.crt
sudo cp /etc/letsencrypt/live/dev.ai4inclusion.org/privkey.pem ./dev.ai4inclusion.key

# Change ownership
sudo chown $USER:$USER dev.ai4inclusion.crt dev.ai4inclusion.key
```

### Step 4: Run SSL Setup Script
```bash
cd /home/ubuntu/AI4inclusion/k8s-manifests-simplified/ssl-certificates
./setup-ssl.sh
```

## Option 2: AWS Certificate Manager (ACM)

### Step 1: Request Certificate in AWS Console
1. Go to AWS Certificate Manager
2. Request a public certificate
3. Add domain: `dev.ai4inclusion.org`
4. Choose DNS validation
5. Validate domains by adding DNS records

### Step 2: Use ACM Certificate with ALB
If you want to use ACM, you'll need to modify the nginx service to use ALB instead of NLB:

```yaml
# In nginx-ingress-controller.yaml, change the service annotations:
annotations:
  service.beta.kubernetes.io/aws-load-balancer-type: nlb
  service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
  # Add these for ACM:
  service.beta.kubernetes.io/aws-load-balancer-ssl-cert: arn:aws:acm:region:account:certificate/certificate-id
  service.beta.kubernetes.io/aws-load-balancer-ssl-ports: https
  service.beta.kubernetes.io/aws-load-balancer-backend-protocol: http
```

## Option 3: Self-Signed Certificate (Testing Only)

### Generate Self-Signed Certificate
```bash
# Generate private key
openssl genrsa -out dev.ai4inclusion.key 2048

# Generate certificate
openssl req -new -x509 -key dev.ai4inclusion.key -out dev.ai4inclusion.crt -days 365 \
  -subj "/C=IN/ST=State/L=City/O=Organization/CN=dev.ai4inclusion.org"

# Run setup script
./setup-ssl.sh
```

## Verification

### Check Certificate
```bash
# Check certificate details
openssl x509 -in ai4inclusion.crt -text -noout

# Test SSL connection
openssl s_client -connect dev.ai4inclusion.org:443 -servername dev.ai4inclusion.org
```

### Test HTTPS
```bash
# Test with curl
curl -I https://dev.ai4inclusion.org

# Test Kong Admin
# Kong Admin is now exposed via the same dev domain if routed accordingly
```

## Auto-Renewal (Let's Encrypt)

### Setup Cron Job
```bash
# Add to crontab for auto-renewal
sudo crontab -e

# Add this line (runs every day at 2 AM)
0 2 * * * /usr/bin/certbot renew --quiet && systemctl reload nginx
```

### Update Certificates in Kubernetes
```bash
# Create a script to update certificates
cat > update-ssl.sh << 'EOF'
#!/bin/bash
sudo certbot renew --quiet
sudo cp /etc/letsencrypt/live/dev.ai4inclusion.org/fullchain.pem ./dev.ai4inclusion.crt
sudo cp /etc/letsencrypt/live/dev.ai4inclusion.org/privkey.pem ./dev.ai4inclusion.key
sudo chown $USER:$USER dev.ai4inclusion.crt dev.ai4inclusion.key
./setup-ssl.sh
EOF

chmod +x update-ssl.sh
```

## Troubleshooting

### Certificate Not Working
1. Check if certificate is valid: `openssl x509 -in ai4inclusion.crt -text -noout`
2. Verify DNS is pointing to your NLB IP
3. Check nginx logs: `kubectl logs -n ingress-nginx deployment/nginx-ingress-controller`
4. Verify TLS secret: `kubectl get secret ai4inclusion-tls-secret -n ingress-nginx -o yaml`

### Common Issues
- **Certificate expired**: Renew with `certbot renew`
- **Wrong domain**: Ensure certificate includes all domains
- **DNS not propagated**: Wait for DNS propagation (up to 48 hours)
- **Firewall blocking**: Check security groups allow port 443


