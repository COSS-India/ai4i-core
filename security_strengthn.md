# AI4I-Core Platform — Security Strategy

## Executive Summary

The strategy covers:

- API Gateway Security (APISIX) — centralized authentication, authorization, rate limiting, and DDoS protection
- Authentication & Authorization — JWT tokens (RS256), API keys
- Password Security — Bcrypt hashing with automatic salting and configurable rounds
- Network Security — TLS enforcement and internal network isolation via API Gateway routing

---

# Architecture Overview

## System Architecture

All client traffic enters exclusively through the APISIX gateway. Backend services are isolated at the network level and accept connections only from the API gateway — they are not exposed to public networks directly. No firewall is required to achieve this isolation.

**Security enforcement is layered:**

- **Layer 1 — Network:** TLS termination at Load Balancer, internal routing via API gateway (no public access to backend services)
- **Layer 2 — Gateway:** Rate limiting (per token), JWT/API key validation, request correlation
- **Layer 3 — Application:** Auth-service enforces password policy, token generation, permission checks

## Security Flow

**1. Request arrives at APISIX Gateway**

- TLS terminated at Load Balancer. Client IP resolved from trusted upstream only (not X-Forwarded-For).

**2. Gateway performs security checks**

- Token-based distributed rate limiting (per token / per user / per API key)
- JWT RS256 verification OR API key validation (via auth-service API with internal Redis cache)

**3. Gateway injects validation headers**

- `X-User-ID`, `X-User-Email`, `X-User-Roles` (from JWT or API key)
- `X-Auth-Source: AUTH_TOKEN | API_KEY | BOTH`
- `X-Validated: true`

**4. Backend services trust gateway headers**

- Backends are only reachable via the API gateway — header trust is safe because direct public access is impossible.
- Auth-service enforces password policy as the authoritative check for all requests.

---

# Network Security & TLS

## TLS Enforcement

**Required:** All traffic must be encrypted. HTTP must redirect to HTTPS. There are no exceptions.

| Traffic Path | Protocol | Certificate |
|---|---|---|
| Client → Load Balancer | TLS 1.2+ (HTTPS) | Public CA certificate (Let's Encrypt or equivalent) |
| LB → APISIX Gateway | TLS 1.2+ | Internal CA certificate (internal PKI) |
| APISIX → Auth Service | TLS 1.2+ | Internal CA certificate (internal PKI) |
| APISIX → ASR / NMT Services | TLS 1.2+ | Internal CA certificate (internal PKI) |
| Internal service-to-service | TLS 1.2+ | Internal CA certificate (internal PKI) |

> **Note:** mTLS (mutual certificate authentication) is not used between APISIX and backend services. The overhead is not justified given that services are only reachable via the gateway.

## Network Isolation

Backend services must not be reachable from outside the internal network. The following controls are in place:

- **API Gateway routing:** Auth-service, ASR, NMT are only accessible via the API gateway. They are not bound to public-facing interfaces — no firewall rules are required to enforce this.
- **TLS enforcement:** All traffic between APISIX and backend services uses TLS.
- **X-Validated trust scope:** The `X-Validated: true` header is trusted exclusively because network controls make impersonating the gateway impossible. If network isolation is ever relaxed, this trust model must be re-evaluated.

---

# API Gateway Security — APISIX

## Feature 1: Distributed Rate Limiting & DDoS Protection

Rate limits are enforced using APISIX `limit-count` (Redis backend) and `limit-req` plugins. All counters are stored in Redis to ensure consistent enforcement across a multi-node APISIX cluster.

> **All rate limiting is enforced at the token level, not by IP address.**

### Rate Limiting Strategies

| Strategy | Key | Use Case |
|---|---|---|
| Per API Token | API token / JWT subject claim | Public endpoints — login, register |
| Per User ID | X-User-ID header | Authenticated endpoints |
| Per User or Token (fallback) | X-User-ID or API token | Protected endpoints — uses user ID when present, token otherwise |
| Per API Key | X-API-Key-ID header | API key-based programmatic access |
| Burst Protection | X-API-Key-ID or X-User-ID | DDoS prevention — applied per token on all endpoints |

### Per-Endpoint Limits

| Endpoint | Rate Limit | Key | Purpose |
|---|---|---|---|
| /api/v1/auth/login | 5 requests / 5 min | X-API-Key-ID or X-User-ID | Brute force prevention |
| /api/v1/auth/register | 3 requests / hour | X-API-Key-ID or X-User-ID | Spam account prevention |
| /api/v1/asr/* | 120 requests / min | X-User-ID or API token | Per-user fair usage |
| /api/v1/asr/* | 200 req/s burst (50 burst allowed) | X-API-Key-ID or X-User-ID | DDoS layer |
| All endpoints | 200 req/min | X-API-Key-ID or X-User-ID | Global token ceiling |

### Redis-Backed Configuration

```yaml
limit-count:
  key: "$http_x_user_id or $http_x_api_key_id"
  count: 120
  time_window: 60
  policy: redis
  redis_host: "redis-host"
  redis_port: 6379
```

### IP Source Trust

APISIX must be configured to resolve the real client IP only from a trusted upstream proxy, not from client-supplied headers. This prevents rate limit bypass via X-Forwarded-For spoofing:

```yaml
real_ip_from:
  - 10.0.0.0/8  # trusted internal load balancer range
real_ip_header: X-Forwarded-For
recursive_real_ip: on
```

---

## Feature 2: JWT Token Verification (RS256)

RS256 asymmetric signing means the private key never leaves auth-service. APISIX only needs the public key to verify tokens, so even if APISIX configuration is compromised, no tokens can be forged.

| Property | RS256 |
|---|---|
| Key type | Private/public key pair (asymmetric) |
| APISIX holds | Public key only — cannot forge tokens |
| Auth-service holds | Private key (signs tokens) |
| Rotation complexity | Public key rotated independently via `kid` header |
| Compromise impact | Leaked public key has no security impact |

### JWT Key Rotation

Tokens include a `kid` (Key ID) header claim. APISIX maintains a JWKS (JSON Web Key Set) endpoint fetched from auth-service. To rotate:

1. Generate new RSA key pair in auth-service
2. Publish new public key at `/.well-known/jwks.json` with a new `kid` value
3. New tokens are signed with the new private key (new `kid`)
4. APISIX validates using the matching public key (by `kid` lookup) — old tokens remain valid until expiry
5. After all old tokens have expired, remove the old key from JWKS

---

## Feature 3: API Key Validation (via Auth-Service API)

APISIX does **not** connect directly to Redis for API key validation. Instead, it calls an auth-service API that internally manages Redis. This keeps Redis access encapsulated within auth-service.

| Step | Action |
|---|---|
| 1. Client sends | `X-API-Key: ak_<key>` |
| 2. APISIX checks local cache | If cached and TTL valid: use cached result, skip auth-service call |
| 3. Cache miss: APISIX calls auth-service API | `POST /api/v1/auth/validate-api-key` |
| 4. Auth-service validates | Key exists, is active, not expired, has required permissions |
| 5. APISIX caches result | TTL: 60 seconds |
| 6. APISIX injects headers | `X-User-ID`, `X-API-Key-ID`, `X-Auth-Source: API_KEY`, `X-Validated: true` |
| 7. Request forwarded to backend | Backend trusts gateway headers |

**Key Revocation:** When an API key is revoked in auth-service, auth-service handles cache invalidation internally. APISIX relies on the 60s TTL as the natural expiry window, or can call the auth-service cache purge API to invalidate immediately.

### APISIX Header Injection

APISIX supports injecting request headers upstream via the `proxy-rewrite` or `request-transformer` plugins. After validating a JWT or API key, APISIX injects:

```yaml
# Example using request-transformer plugin
plugins:
  request-transformer:
    add:
      headers:
        - "X-User-ID: {user_id}"
        - "X-User-Email: {email}"
        - "X-User-Roles: {roles}"
        - "X-Auth-Source: API_KEY"
        - "X-Validated: true"
```

---

## Feature 4: Password Strength Validation (Auth-Service Only)

Password strength validation is handled exclusively by auth-service. APISIX does not perform any password pre-validation — this is not within its responsibility.

| Layer | Location | Purpose | Behavior on Failure |
|---|---|---|---|
| Authoritative | Auth-service (Python) | Enforce password policy for all requests | 400 Bad Request with structured error response |

Password requirements (enforced by auth-service):

- Minimum 8 characters
- At least one uppercase letter (A–Z)
- At least one lowercase letter (a–z)
- At least one digit (0–9)
- At least one special character (`!@#$%^&*` etc.)

---

## Feature 5: Multi-Mode Authentication

| Mode | JWT Required | API Key Required | Use Case |
|---|---|---|---|
| AUTH_TOKEN | ✅ Yes | No | User session via web or mobile app |
| API_KEY (default) | No | ✅ Yes | Programmatic access, scripts, integrations |
| BOTH | ✅ Yes | ✅ Yes | Both must be valid and ownership must match |

If the `X-Auth-Source` header is omitted, the gateway defaults to `API_KEY` mode. In `BOTH` mode, the API key must belong to the same user as the JWT subject claim — a mismatch is rejected.

---

# Authentication & Authorization

## Token Lifecycle

| Token Type | Expiry | Storage Guidance | Revocation |
|---|---|---|---|
| Access Token (JWT) | 15 minutes | In-memory only (never localStorage in browser) | Expires naturally — short TTL limits exposure window |
| Refresh Token (JWT) | 7 days | HttpOnly, Secure, SameSite=Strict cookie | `POST /api/v1/auth/revoke` — invalidates server-side; Redis revocation list checked on each refresh |

### Refresh Token Rotation

Every use of a refresh token issues a new refresh token and invalidates the old one (rotation). This limits the window of exposure if a refresh token is stolen:

- Client calls `POST /api/v1/auth/refresh` with current refresh token
- Auth-service validates token, checks it has not been revoked
- New access token and new refresh token are issued
- Old refresh token is immediately added to Redis revocation list (TTL = original token expiry)
- If a revoked refresh token is presented, all sessions for that user are terminated (replay attack detection)

---

# Password Security

## Algorithm: Bcrypt

Bcrypt is the industry-standard password hashing function. It uses EksBlowfish (expensive key schedule Blowfish) to make hashing computationally expensive and resistant to brute force.

### Hash Format

```
$2b$14$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5Gy...
 │   │  │─────────────────│  │─────────────────────│
 │   │  Salt (22 chars)      Hash (31 chars)
 │   └─ Rounds (cost factor: 14 = 2^14 = 16,384 iterations)
 └─ Algorithm identifier ($2b$ = current bcrypt standard)
```

### Rounds Configuration

| Rounds | Iterations | Approx. Time | Recommended Use |
|---|---|---|---|
| 10 | 1,024 | ~0.1s | Development only — never production |
| 12 | 4,096 | ~0.3s | Development only |
| 14 | 16,384 | ~1.2s | ✅ Production standard — current setting |
| 16 | 65,536 | ~5s | High-security accounts (admin, privileged users) |

### Security Properties

| Property | How Implemented | Threat Mitigated |
|---|---|---|
| Automatic salt generation | `os.urandom()` — 16 bytes (128 bits) per password, embedded in hash string | Rainbow table attacks |
| One-way hashing | Blowfish cipher in one-way mode — mathematically irreversible | Database leaks — hashes cannot be reversed |
| Adaptive cost | `BCRYPT_ROUNDS` env variable — can be increased as hardware improves | Hardware advances |
| Constant-time comparison | `passlib verify()` uses constant-time comparison | Timing attacks |

### Configuration

```python
# auth-service environment
BCRYPT_ROUNDS=14  # Production
BCRYPT_ROUNDS=10  # Development only

# auth_utils.py
BCRYPT_ROUNDS = int(os.getenv('BCRYPT_ROUNDS', '14'))
pwd_context = CryptContext(
    schemes=['bcrypt'],
    default='bcrypt',
    bcrypt__rounds=BCRYPT_ROUNDS
)
```

---

# Implementation Status

| Feature | Status | Location |
|---|---|---|
| APISIX Rate Limiting (token-based) | ✅ Implemented | apisix.yaml — all `limit-count` blocks use `policy: redis`, `key: http_x_user_id` |
| JWT RS256 Verification at Gateway | ✅ Implemented | apisix.yaml — `forward-auth` on 27 authenticated routes |
| JWT Key Rotation (kid / JWKS) | ✅ Implemented | auth-service `jwks.py`, `auth_utils.py` (kid header), APISIX `/.well-known/jwks.json` route |
| API Key Validation via Auth-Service API | ✅ Implemented | apisix.yaml — `forward-auth` delegates to auth-service `/api/v1/auth/validate` |
| API Key Revocation (auth-service managed) | ✅ Implemented | auth-service `validate_api_key()` checks `is_revoked` flag |
| Password Strength — Auth-service (sole layer) | ✅ Implemented | auth_utils.py `validate_password_strength()` |
| Password Strength — Gateway pre-check (removed) | ➖ Removed | — |
| Multi-Mode Authentication | ✅ Implemented | apisix.yaml — `serverless-pre-function` Lua on all authenticated routes |
| Bcrypt Password Hashing (rounds=14) | ✅ Implemented | auth_utils.py — `BCRYPT_ROUNDS` env var, `bcrypt__rounds=BCRYPT_ROUNDS` |
| TLS Enforcement (client → LB → gateway) | ✅ Implemented | config.yaml — SSL listener on port 8443 |
| TLS (gateway → backends, no mTLS) | ⏳ Deferred | Deferred to service mesh for automatic mTLS (upstream `scheme: http` unchanged) |
| Network Isolation (API gateway routing) | ✅ Implemented | docker-compose.yml — Postgres, Redis, ES, InfluxDB, Unleash ports removed |
| Refresh Token Rotation | ✅ Implemented | auth-service main.py — rotation + Redis revocation + replay-attack detection |
| IP Spoofing Protection (trusted upstream) | ✅ Implemented | config.yaml — `real_ip_header`, `real_ip_from` with RFC 1918 ranges |
| Gateway Auth Consolidation | ✅ Implemented | `libs/ai4icore_gateway_auth/` — 15 backend auth providers simplified |
| Credential Cleanup (hardcoded SMTP password) | ✅ Implemented | alertmanager.yml — replaced with `${SMTP_PASSWORD}` env var |
| Integration Test Suite | ✅ Implemented | `tests/integration/test_gateway_security.py`, `test_token_rotation.py` |

## Required Configuration

| Variable | Service | Value | Status |
|---|---|---|---|
| JWT_RS256_PRIVATE_KEY_PATH | auth-service | Path to RSA private key (PEM) | ✅ Templated in env.template (`/app/keys/private.pem`) — generate key pair before deploy |
| JWT_RS256_PUBLIC_KEY_PATH | auth-service, APISIX | Path to RSA public key (PEM) | ✅ Templated in env.template (`/app/keys/public.pem`) — generate key pair before deploy |
| JWT_KEY_ID | auth-service | Key identifier for JWKS kid header | ✅ Templated (`auth-key-1`) |
| BCRYPT_ROUNDS | auth-service | 14 (production) | ✅ Templated and implemented |
| REDIS_HOST / REDIS_PORT / REDIS_PASSWORD | APISIX, auth-service | Redis instance for rate limiting and token revocation | ✅ Templated and used in apisix.yaml |
| SMTP_PASSWORD | alertmanager | Gmail app password for alert emails | ✅ Templated — ⚠️ rotate the old password (was committed to git history) |
| INTERNAL_CA_CERT | All services | Internal CA certificate for TLS (gateway → backends) | ⏳ Deferred to service mesh |

---

# Recommendations

## Immediate (Before Production)

- **Set all required environment variables:** JWT private/public key paths, Redis connection, internal CA certificates. None of the security controls function correctly without these.
- **Verify TLS between APISIX and all backends:** Test that a direct request to auth-service (bypassing APISIX) is rejected.
- **Validate token-based rate limiting:** Run a multi-node APISIX cluster and confirm rate limit counters are shared across nodes and keyed by token, not IP.
- **Remove duplicate validation from backend services:** Backends can fully trust `X-Validated: true` headers. Remove any remaining JWT/API key checks in ASR, NMT, and other services.
- **Confirm APISIX header injection:** Verify that `X-User-ID`, `X-User-Email`, `X-User-Roles`, and `X-Auth-Source` are correctly injected by APISIX on all authenticated routes.

---

# Next Steps

| Phase | Task | Owner |
|---|---|---|
| Phase 1 — Production Readiness | Set all required environment variables | DevOps |
| Phase 1 — Production Readiness | Verify TLS enforcement end-to-end | DevOps / Security |
| Phase 1 — Production Readiness | Validate token-based rate limiting under load | Platform |
| Phase 1 — Production Readiness | Run full auth flow test suite | Backend |
| Phase 2 — Optimization | Remove duplicate validation from ASR / NMT | Backend |

---

# Security Posture Summary

| Aspect | Status | Notes |
|---|---|---|
| Authentication | ✅ Strong | RS256 JWT + API key with caching and revocation |
| Authorization | ✅ Strong | RBAC via Casbin, permission-checked at gateway and auth-service |
| Password Security | ✅ Strong | Bcrypt rounds=14, auth-service only, constant-time comparison |
| Transport Security | ✅ Strong | TLS termination at LB, TLS gateway→backends (no mTLS) |
| Network Isolation | ✅ Strong | API gateway routing — backends not exposed to public networks |
| Rate Limiting | ✅ Strong | Token-based, distributed, per-token/user/key with DDoS burst protection |
| Token Lifecycle | ✅ Strong | Short access tokens, rotating refresh tokens, revocation endpoint |
| Key Management | ✅ Strong | Asymmetric RS256, kid-based rotation, no shared secrets at APISIX |
| Secret Management | ⚠️ Action Required | All secrets must be set in environment before production |

---

# File Locations & Environment Variables

## File Locations

| Component | Path |
|---|---|
| APISIX Configuration | `services/api-gateway-service/gateways/apisix/apisix.yaml` |
| Auth Service Utils | `services/auth-service/auth_utils.py` |
| Auth Service Main | `services/auth-service/main.py` |
| Environment Template | `services/auth-service/env.template` |
| Password Security Docs | `services/auth-service/PASSWORD_SECURITY.md` |
| APISIX Implementation Guide | `services/api-gateway-service/gateways/apisix/IMPLEMENTATION_GUIDE.md` |

## Environment Variables

| Variable | Service | Description |
|---|---|---|
| JWT_PRIVATE_KEY_PATH | auth-service | RSA private key for signing JWT tokens (RS256) |
| JWT_PUBLIC_KEY_PATH | APISIX | RSA public key for verifying JWT tokens |
| JWKS_ENDPOINT | APISIX | URL to auth-service JWKS endpoint for key rotation |
| BCRYPT_ROUNDS | auth-service | 14 (production), 10 (development) |
| REDIS_HOST | auth-service | Redis host for rate limiting and API key cache |
| REDIS_PORT | auth-service | Redis port (default: 6379) |
| INTERNAL_CA_CERT | All services | Internal CA certificate for TLS |