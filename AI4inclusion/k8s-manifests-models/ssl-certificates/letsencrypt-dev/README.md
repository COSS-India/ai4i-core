# Let's Encrypt for dev.ai4inclusion.org

This folder provisions a Let's Encrypt TLS certificate for `dev.ai4inclusion.org` using cert-manager and the nginx ingress HTTP-01 solver.

## Prerequisites
- cert-manager installed in the cluster (CRDs + controller)
- `dev.ai4inclusion.org` DNS A/ALIAS pointing to the public address of your nginx ingress controller
- nginx ingress class is `nginx` (default for `ingress-nginx`)

## Apply
```bash
# From repo root
kubectl apply -k k8s-manifests-models/ssl-certificates/letsencrypt-dev
```

This creates:
- ClusterIssuer `letsencrypt-prod`
- Certificate `dev-ai4inclusion-org` in namespace `ingress-nginx`
- TLS Secret `dev-ai4inclusion-org-tls` (created automatically by cert-manager)

## Use the secret in your Ingress
Reference the secret in any Ingress serving `dev.ai4inclusion.org`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: your-service
  annotations:
    kubernetes.io/ingress.class: nginx
spec:
  tls:
  - hosts:
    - dev.ai4inclusion.org
    secretName: dev-ai4inclusion-org-tls
  rules:
  - host: dev.ai4inclusion.org
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: your-service
            port:
              number: 80
```

## Notes
- Certificate auto-renews via cert-manager/ACME. No manual secret updates required.
- Update the email in `cluster-issuer.yaml` if you prefer a different contact for expiry notices.






