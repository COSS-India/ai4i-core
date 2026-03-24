# RS256 Key Rotation Procedure

## Overview

Auth-service uses RS256 (RSA + SHA-256) with multiple key pairs for JWT signing.
Key rotation allows transitioning to a new signing key without invalidating
existing tokens.

## Key Storage

Keys are PEM files stored in the directory specified by `RS256_KEY_DIRECTORY`:

```
keys/
├── key_01_private.pem
├── key_01_public.pem
├── key_02_private.pem
├── key_02_public.pem
├── ...
├── key_10_private.pem
└── key_10_public.pem
```

## Production Requirements

- **Minimum 10 key pairs** (configurable via `RS256_MIN_KEY_COUNT`)
- Keys MUST be pre-provisioned — auto-generation is **disabled** in production/staging
- Mount via Docker volume or Kubernetes secret
- All replicas MUST share the same key directory

## Rotation Steps

### 1. Generate a new key pair

```bash
# Generate new key pair (e.g., key_11)
openssl genrsa -out key_11_private.pem 2048
openssl rsa -in key_11_private.pem -pubout -out key_11_public.pem
```

### 2. Deploy the new key to all replicas

Add the new PEM files to the shared volume/secret. All replicas will
load it on next restart.

### 3. Update the active key index

Set `RS256_ACTIVE_KEY_INDEX` to the new key's index (e.g., `10` for key_11,
since indices are 0-based on the sorted file list).

### 4. Restart auth-service

Rolling restart. New tokens will be signed with the new key.
Old tokens remain valid because the old public key is still loaded.

### 5. Wait for old tokens to expire

- Access tokens: max 1 hour
- Refresh tokens: max 7 days
- API keys: max 1 year

### 6. (Optional) Remove old keys

After all tokens signed with the old key have expired, you can remove
the old key pair. For API keys with 1-year expiry, this means waiting
1 year or revoking and re-issuing.

## Verification

The JWKS endpoint exposes all loaded public keys:

```bash
curl http://auth-service:8081/api/v1/auth/.well-known/jwks.json
```

Other services fetch this JWKS to verify tokens. After rotation, they
will automatically pick up the new key on their next JWKS refresh.

## Emergency Key Compromise

If a private key is compromised:

1. Remove the compromised key pair from the directory
2. Restart all replicas immediately
3. All tokens signed with the compromised key will become invalid
4. Users will need to re-login; API keys will need to be re-issued
