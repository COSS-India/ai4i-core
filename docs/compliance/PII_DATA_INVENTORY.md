# PII Data Inventory — AI4I-Orchestrate Platform

| | |
|---|---|
| **Document purpose** | Inventory of all Personally Identifiable Information (PII) collected, stored, or processed by the AI4I-Orchestrate platform, for DPG certification review and privacy compliance. |

---

## 1. Executive summary

The platform consists of three backend services (auth-service, platform-core-service, inference-service), a web frontend, and supporting infrastructure (PostgreSQL, Redis, Kafka, OpenSearch, Prometheus).

- **Direct PII stored:** email addresses, usernames, full names, phone numbers, avatar URLs, tenant contact details, and notification recipient emails — all in PostgreSQL.
- **Conversation history / model inputs and outputs are NOT persisted.** The inference service is stateless; user text, audio, and images are processed in memory and forwarded to model backends. The PII redaction service likewise processes text transiently and stores only metadata (counts, timings) in its audit log.
- **Indirect / technical identifiers** (user UUIDs, tenant UUIDs, client IP addresses, API key IDs) appear in application logs, OpenTelemetry traces, and Prometheus metrics.
- **No privacy policy exists in the repository today** (see Section 8). The closest material is the "Regulatory Compliance & Privacy" section of `docs/architecture/00-overview.md`.
- **No self-service data export or erasure flows exist.** User deletion is an admin-initiated soft delete; data-subject rights (GDPR / DPDPA) must be implemented by the operator.

---

## 2. PII inventory by data type

| # | PII type | Examples | Collected from | Stored in | Retention (default) |
|---|----------|----------|----------------|-----------|---------------------|
| 1 | Email address | Registration, login, Google OAuth, tenant contact, alert recipients | Registration/login forms, OAuth, admin tenant forms | Postgres `users.email`, `tenants.email`, `notification_receivers.email_to`; browser sessionStorage; Alertmanager YAML on disk | Indefinite (soft delete only) |
| 2 | Username | Derived from email local-part or chosen | Registration | Postgres `users.username`; sessionStorage | Indefinite |
| 3 | Full name | Registration, profile, Google OAuth | Forms / OAuth | Postgres `users.full_name`, `tenants.name`; sessionStorage | Indefinite |
| 4 | Phone number | Optional at registration / profile / tenant creation | Forms | Postgres `users.phone_number`, `tenants.phone_number` | Indefinite |
| 5 | Avatar / profile image URL | Google OAuth, profile update | OAuth / forms | Postgres `users.avatar_url` | Indefinite |
| 6 | Password | Registration, login, reset | Forms | Postgres `user_credentials` as **Argon2id hash + per-user salt** (never plaintext) | Until changed; row removed on user hard delete (cascade) |
| 7 | Authentication tokens | Refresh tokens, email-verification / setup / password-reset tokens (JWTs; setup/verify/reset tokens embed the email claim) | Issued by auth-service | Postgres `refresh`, `token_verification`; Redis (OAuth exchange); sessionStorage (encrypted) | Refresh: 7 days; setup/verify: 48 h; reset: 30 min; rows deactivated but not purged |
| 8 | API keys | 32-char hex secrets linked to a user | Generated on request | Postgres `api_key` (plaintext), Redis cache | 365 days (configurable); revocable |
| 9 | Organisation / tenant data | Org name, contact name, contact email/phone | Tenant onboarding forms | Postgres `tenants` | Indefinite |
| 10 | Submitter / team names | Model registry metadata: person names, "about me" text, OAuth IDs | Model submission API | Postgres `mm_models.submitter` (JSONB); Redis cache | Indefinite |
| 11 | Usage / billing records | `tenant_id`, `api_key_id`, service, units, cost (no names/emails) | Generated per API call | Postgres `usage_records`, `wallet_*`, `quota_usage`; Redis counters | Postgres: indefinite; Redis counters: 1 h – 14 days TTL |
| 12 | Access / activity logs | Client IP address, HTTP method/path, user UUID, tenant UUID, timestamps | All HTTP requests | stdout → Fluent Bit → OpenSearch `logs-*` indices | Kafka transport: 7 days; **OpenSearch: no expiry configured** |
| 13 | Telemetry traces | Trace/span data with `userId`, `tenantId`, endpoint, token counts (no prompt text) | Inference requests | Kafka → OpenSearch `traces-*` | Kafka: 7 days; **OpenSearch: no expiry configured** |
| 14 | Metrics | Aggregates labelled by tenant UUID, service, endpoint (no raw content) | All requests | Prometheus TSDB | 30 days |
| 15 | Last login / behavioural | `users.last_login` timestamp | Login events | Postgres `users` | Indefinite |
| 16 | User-generated content (may embed PII) | Translation text, chat/LLM prompts, audio, images, OCR documents | Inference API requests | **Not persisted** — processed in memory, forwarded to model backends, returned in response | Transient (request lifetime) |
| 17 | PII redaction audit metadata | Tenant ID, entity counts, processing steps — **not the detected PII values or input text** | `/pii/redact` calls | Postgres `pii_audit_logs` | Indefinite |
| 18 | Alert history | Alert names, tenant org names, label/annotation JSON | Alertmanager webhooks | Postgres `alert_history` | Indefinite (append-only) |
| 19 | Anonymous session ID | Random UUID for unauthenticated "try it" usage | Generated client-side | Browser sessionStorage; sent as `X-Anonymous-Session-Id` header | Browser session |

**Not collected anywhere:** government IDs as account data, payment card numbers, precise geolocation, biometric templates, third-party analytics/tracking cookies. (Users may *submit* such data inside inference text — see row 16 — which is why the PII redaction guardrail exists.)

---

## 3. Where PII is stored (per data store)

### 3.1 PostgreSQL — `ai4iplatform_auth` (auth-service)

| Table | PII fields | Protection |
|-------|-----------|------------|
| `users` | email, username, full_name, phone_number, avatar_url, last_login, timezone | Plaintext at application layer; soft delete (`is_delete=True`) |
| `user_credentials` | password_hash, password_salt | Argon2id hashing |
| `tenants` | contact name, organisation, email, phone_number | Plaintext |
| `refresh` | refresh-token JWT (session secret) | RS256-signed, stored unhashed |
| `token_verification` | setup/verify/reset JWTs (embed email claim) | Single-use flag; deactivated rows not purged |
| `api_key` | API key secret, key name, user linkage | Stored unhashed |
| `user_role`, `audit` (legacy, unused) | user UUIDs; legacy `audit.subject/details` could hold PII but no code writes to it | — |

### 3.2 PostgreSQL — `ai4iplatform_core` (platform-core-service)

| Table | PII fields | Protection |
|-------|-----------|------------|
| `notification_receivers` | **email_to[]** (recipient email arrays), tenant org name | Plaintext |
| `alert_history` | tenant org names; label/annotation JSON from alert payloads | Plaintext, append-only |
| `mm_models` | submitter/team person names, aboutMe text, OAuth IDs (JSONB) | Plaintext |
| `mm_services` | service API keys (secrets, not personal data) | Plaintext |
| `usage_records`, `wallet_*`, `quota_usage` | tenant_id, api_key_id (pseudonymous identifiers only) | API responses mask key IDs |
| `pii_audit_logs` | trace_id, tenant_id, counts, step summaries — **no input text or detected values** | Metadata-only by design |
| `pii_tenant_domain_map`, `pii_domain_policies`, `pii_pattern_library` | Tenant IDs and redaction rules (reference data, no personal values) | — |

### 3.3 Redis (ephemeral cache)

| Keys | PII content | TTL |
|------|-------------|-----|
| `auth:apikey:{key}` | API key, user_id, tenant_id, permissions | Matches key expiry |
| `auth:oauth_exchange:{code}` | Full login response incl. access + refresh tokens | 2 minutes |
| `auth:oauth_state:{state}` | OAuth redirect metadata | 10 minutes |
| `policy:{tenant_id}` | Tenant name + plan metadata | 1 hour |
| Rate-limit / quota counters | tenant_id, api_key_id (identifiers only) | 1 hour – 14 days |

### 3.4 Browser storage (frontend)

| Storage | Content | Protection |
|---------|---------|------------|
| sessionStorage | Access/refresh JWTs (AES-encrypted with a public env key), `user` profile JSON (email, name, phone, roles), login timestamp, anonymous session ID | Cleared on tab close/logout; AES wrapping is obfuscation, not server-grade protection |
| localStorage | Cross-tab logout timestamp only | No PII |
| Cookies | None used for auth or analytics; **no third-party analytics SDKs** | — |

### 3.5 Observability pipeline

| System | PII content | Retention |
|--------|-------------|-----------|
| Application logs (stdout → Fluent Bit → OpenSearch `logs-*`) | client IP, user UUID, tenant UUID, request paths; emails appear in a few specific log lines (OAuth user creation, tenant provisioning, dev email provider) | **No index lifecycle/delete policy configured** |
| Traces (Kafka → OpenSearch `traces-*`) | userId, tenantId, endpoint, token counts; no prompt/response text in inference spans | Kafka topic: 7 days; OpenSearch: no expiry |
| Prometheus metrics | tenant UUID labels, aggregates only | 30 days |
| Grafana / OpenSearch Dashboards | Visualise the above | Per source |

### 3.6 Files on disk

| File | PII content |
|------|-------------|
| `alertmanager.yml` (generated when alert sync is enabled) | Resolved recipient **email addresses** and SMTP credentials |
| `keys/*.pem` | RS256 signing keys (critical secrets, not personal data) |

### 3.7 Third-party / outbound flows

| Recipient | Data sent | Purpose |
|-----------|-----------|---------|
| Email provider (Amazon SES / SMTP, operator-configured) | Recipient email, display name, token URLs (verification/setup/reset links) | Transactional email; TLS in transit |
| Google OAuth (if enabled) | OAuth flow; platform **receives** email, name, picture; Google tokens are **not stored** | Social login |
| Model backends (Triton / LLM endpoints, operator-configured) | Full inference payloads (text, audio, images, chat messages) | Inference; not stored by the platform |
| External NER service / LLM (PII guardrail) | Text submitted to `/pii/redact`; admin example text for regex generation | PII detection; not stored by the platform |

---

## 4. Retention summary

| Data | Default retention | Mechanism |
|------|-------------------|-----------|
| User accounts and profile PII | **Indefinite** | Soft delete only (`is_delete=True`); no purge job |
| Password hashes | Until password change / user removal | Cascade delete with user row |
| Access JWT | 60 minutes | Token expiry |
| Refresh token | 7 days | Token expiry; row deleted on logout/reset |
| Email verification / setup token | 48 hours | JWT expiry; DB row deactivated, **not deleted** |
| Password reset token | 30 minutes | JWT expiry; single-use |
| API keys | 365 days (configurable) | Expiry + revocation; not hashed at rest |
| OAuth exchange code (Redis) | 2 minutes | Redis TTL |
| Usage/billing records, wallets | **Indefinite** | No archival/purge |
| PII redaction audit metadata | **Indefinite** | No purge |
| Alert history | **Indefinite** | Append-only |
| Logs/traces in Kafka | 7 days | Topic retention |
| Logs/traces in OpenSearch | **Indefinite** (no ILM policy) | Manual deletion only |
| Metrics (Prometheus) | 30 days | TSDB retention flag |
| Browser session data | Browser session | sessionStorage semantics |
| Inference content (text/audio/images) | **Not retained** | Stateless processing |

---

## 5. Who has access to PII

Access is enforced in two layers: the API gateway maps each endpoint to a required permission (via `api_permissions.json` and `/auth/validate`), and services apply additional role/tenant-scope checks.

| Role | Access to PII |
|------|---------------|
| **End user (USER)** | Own profile only (`GET/PUT /auth/me`); own API keys; can update name/phone/timezone/avatar (not email) |
| **GUEST** | Own minimal profile; limited inference; no access to other users' data |
| **TENANT_ADMIN** | Full PII (email, name, phone) of users **within their own tenant only**; tenant-scoped traces; PII guardrail admin for their domain; cross-tenant access blocked (404) |
| **MODERATOR** | User create/update/delete permissions and all-tenant telemetry, but **blocked from tenant user listings and individual user PII reads** at the service layer; can list all API keys (which exposes owner email/username) |
| **ADMIN** | All users, all tenants, all PII, all audit logs and traces |
| **Platform operator (infrastructure access)** | Direct access to PostgreSQL, Redis, OpenSearch, Prometheus, Docker logs — i.e., all stored PII. The local OpenSearch configuration has the security plugin **disabled**, so log/trace data is unprotected at that layer in default local deployments |
| **Third parties** | Email provider sees recipient addresses; Google sees OAuth flow; model backends see inference payloads in transit |

---

## 6. How PII is protected

| Control | Status |
|---------|--------|
| Password hashing | Argon2id with per-user salt |
| Token signing | RS256 JWTs; access tokens carry user UUID only (no email); private keys on disk |
| Transport encryption | TLS terminated at gateway; SMTP TLS for outbound email |
| Tenant isolation | Enforced in queries and route guards (tenant admins scoped to own tenant) |
| PII redaction guardrail | `/pii/redact` detects and redacts PHONE, EMAIL, AADHAAR, PAN, names, locations etc. via regex + NER, with domain policies; audit log stores metadata only |
| Anti-enumeration | Forgot-password and resend flows return generic responses (note: `GET /auth/check-email` does reveal existence) |
| Log hygiene | Endpoint-validation logs redact `authorization`/`api_key`/`password` keys and strip URL credentials; inference error paths redact backend URLs |
| Browser tokens | AES-wrapped in sessionStorage; cleared on logout; cross-tab logout signal |
| Database auth | Postgres SCRAM-SHA-256; Redis optional password |

---

## 7. Data-subject rights (current state)

| Capability | Status |
|------------|--------|
| View own data | Partial — `GET /auth/me` returns profile; no consolidated export of usage/logs |
| Rectification | Partial — users can edit name/phone/timezone/avatar; email is not self-editable |
| Deletion / erasure | **Admin-initiated soft delete only** (`DELETE /auth/tenants/{id}/users/{user_id}`); no self-service deletion; PII retained in DB and observability stores |
| Data portability / export | **Not implemented** |
| Consent management | Not implemented (registration implies consent; no consent records) |

Per `docs/architecture/00-overview.md`, GDPR/DPDPA data-subject rights are explicitly delegated to the deploying operator. For DPG certification, this delegation must be stated in the privacy policy, and operators need documented procedures (or built-in features) for erasure and export.

---

## Appendix A — Key source references

| Topic | Path |
|-------|------|
| User model | `services/auth-service/app/models/user.py` |
| Credentials / hashing | `services/auth-service/app/models/credentials.py`, `app/core/security.py` |
| Tokens | `services/auth-service/app/models/refresh.py`, `app/models/verification.py` |
| API keys | `services/auth-service/app/models/api_key.py` |
| Tenants | `services/auth-service/app/models/tenant.py` |
| Token/key TTL config | `services/auth-service/app/core/config.py` |
| Soft delete | `services/auth-service/app/services/tenant_service.py` (delete flow) |
| Notification recipient emails | `services/platform-core-service/app/models/alert_management/notification_receiver.py` |
| PII redaction audit | `services/platform-core-service/app/models/pii_management/audit_log.py` |
| Usage/billing | `services/platform-core-service/app/models/pay_per_use/` |
| Model submitter names | `services/platform-core-service/app/models/model_management/model.py` |
| Access log middleware (client IP) | `libs/ai4i_core/ai4i_core/logging/middleware.py` |
| Trace user/tenant attributes | `services/inference-service/trace/request_span.py` |
| Frontend token/profile storage | `frontend/simple-ui/src/utils/tokenStorage.ts`, `src/services/authService.ts` |
| Kafka retention | `infrastructure/kafka/init-kafka.sh` |
| Prometheus retention | `docker-compose-local.yml` |
| RBAC roles and permissions seed | `infrastructure/databases/migrations/postgres/alembic/versions/ai4iplatform_auth/2362774ac241_seed_default_data.py` |
| Gateway permission map | `services/auth-service/api_permissions.json` |
| Compliance architecture notes | `docs/architecture/00-overview.md` |
