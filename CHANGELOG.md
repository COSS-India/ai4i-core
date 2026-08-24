# Changelog

All notable changes to AI4I-Orchestrate are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).


## [2.5.0] - 2026-08-24

> Metering and usage release, 67 PRs merged

### Added
- Usage Viewer role, a restricted role with access to the Usage Dashboard and Profile only (renamed from Program Admin before release)
- Model Usage across the Metering Dashboard, with model-registry summary KPIs and a top-models ranking
- LLM Usage Metering Dashboard
- Allocated and remaining budget and token totals on the usage summary
- Onboarding Guide for Institution Admin, with navigation for Institution and Adopter Admins
- Runtime-configurable AI Switch branding: product name and adopter logo (`ADOPTER_LOGO_URL`) read from the pod environment, so rebranding needs no image rebuild
- Swagger schema coverage for auth-service, platform-core and inference requests/responses

### Changed
- Metering keys usage on an immutable organisation id alongside the display name, so renaming an organisation keeps its history attached
- Metering counts only billable traffic: requests are labelled by how the caller authenticated, and the dashboards restrict to API-key traffic
- Service schema aligned to the ULCA deployment-service spec, with inference-endpoint fields on services and the schema derived from the linked model when omitted
- Role names consolidated into a single source of truth; organisation listing and detail authorise on the `x-permission-id` header instead of DB role checks
- "Tenants" renamed to "Institutions" across the application
- Unused per-service policy field removed
- Service Usage tab removed from the Usage Dashboard
- Auth-service pay-per-use notification retried instead of dropped on failure

### Fixed
- Ghost service IDs, services no longer in the registry, excluded from Model Consumption
- Active Tenants count includes only ACTIVE-status organisations
- Model count made consistent across the Model Registry UI, the list-models API and the Usage Dashboard
- Malformed API keys return 401 instead of falling through as valid
- Organisation admins can no longer deactivate their own account
- Tenant-user responses return roles as a list, and the UI handles users holding multiple roles
- Trace details no longer report Environment as "development" on staging
- Logs Dashboard card counts
- Tier assignments listed without the active-only filter, and budget API upper-bound validation

### Upgrade notes
- Shared library `ai4i-core` 1.0.17 to 1.0.22, adding the usage-attribution labels the dashboards query
- Deploy order matters: services must run `ai4i-core` 1.0.22 before this release serves the metering dashboards. On an older library the new labels are absent and the dashboards read empty.
- Migrations: three on the auth database (seed the restricted role, grant it read access, rename it to Usage Viewer), two on the core database (ULCA inference-endpoint fields, drop the per-service policy column)
- Contains the 2.4.1 hotfix

---

## [2.4.0] - 2026-08-11

> AI Switch 1.0, 88 PRs merged

### Added
- SSE streaming and metering for LLM chat, a dedicated `/llm/try-it` endpoint, and LLM-only tiers
- `ENABLED_TASK_TYPES` runtime filter over the UI, the service catalogue and tier quotas, applied without a rebuild
- Model Consumption: metering endpoint and the UI to drive it
- Guest LLM inference, with matching UI permission handling
- Endpoint validation before service creation, and bulk endpoint updates on `PATCH /services`
- AI Switch 1.0 branding, plus legal pages and the registration consent flow

### Changed
- Front end scoped to the LLM model task type across modules
- `NEXT_PUBLIC_*` build-time variables replaced with server-side runtime environment config
- Metered units aligned with the quantities pay-per-use actually bills, and the Prometheus tenant label carries the organisation name
- `inferenceEndPoint` removed, with `adapterConfig` and `schema` exposed as top-level fields
- Query parameter `modelTaskType` renamed to `taskTypes`, with comma-separated filters on tiers, traces and usage endpoints
- Pay-per-use consumer switched from async to sync, with fewer DB round-trips and the billed-key dedup TTL cut from 24h to 1h
- Consumer moved off its bespoke DB registry onto the shared bootstrap database
- AI4I-Core renamed to AI4I-Orchestrate in the docs

### Fixed
- API-key status kept in sync with organisation status, including on suspend and deactivate
- Cached billing flags no longer diverge from Redis on refresh
- Logout invalidates the access token, and a password change invalidates other active sessions
- `avg_rps` no longer rounds sparse 24h, 7d and 30d traffic to a misleading 0
- Unsupported `task_types` rejected with 422 instead of returning a 2xx
- Assign-tier budget field keeps precision at extreme values
- Default Organisation protected from status changes and TENANT_ADMIN assignment
- Anonymous Try It Now flow

### Security
- Open-redirect finding closed by sanitising an HTTP parameter
- `String#replace()` replaced with `String#replaceAll()`
- Private endpoint hosts allowed by configuration, with rejected service writes logged
- UUID fallback and guarded API-key copy for insecure browser contexts

### Upgrade notes
- Shared library `ai4i-core` 1.0.8 to 1.0.17
- Migrations: three on the auth database (API-key caching, its JSONB/GIN conversion, the Guest LLM inference grant), five on the core database (service response schema, adapter-config key normalisation, the LLM target-language fix, per-task-type Try It defaults)
- Configuration: `NEXT_PUBLIC_*` front-end variables move to the pod environment or ConfigMap rather than image build time
- A 2.4.1 hotfix shipped on top of this line and was never tagged. It is contained in 2.5.0.

---

## [2.3.0] - 2026-07-27

> Pay-per-use and tier management release, 111 PRs merged

### Added
- Pay-per-use billing across modalities: text, TTS and audio (ASR, diarization, language detection), audio billed on fractional minutes
- Tier Management end to end: scheduled tier and quota changes, tenant reassignment, and pending-quota edits with tenant-admin email notification
- Tier entitlement enforcement on both the API-key and JWT inference paths, including LLM chat completions
- Usage and Spend dashboards: new Usage Dashboard UI, per-model-task-type usage and spend, and a billing-period selector
- Tenant lifecycle status transitions
- Unit Size field on service creation

### Changed
- LLM follows the OpenAI spec: the `model` field is the service identifier for chat and audio endpoints, resolved via MMS, with no custom `serviceId`
- 1:1 mapping enforced between model name and LLM service name
- Model registry schema aligned to the ULCA model spec, with provider and language fields and Swagger docs
- LLM billing decision sourced from `mm_services.task_type` instead of the span attribute
- `serviceId` is now a mandatory, user-supplied field on service creation
- `GET /services` field-filtered for non-admin and public callers instead of returning 403
- Traces routed exclusively through Kafka, with stdout span logging removed
- Service-entity caching moved from Redis to an in-memory cache
- `ai4i-core` bumped to 1.0.8 and published to PyPI

### Fixed
- Budget consumption and usage update after successful inference
- `reset_all_quota_fields` scales to lakhs of API keys
- Missing tier or task-type mapping treated as quota-gated
- Quota Summary usage calculation and the Total Spend card mismatch
- Metering alert PromQL matches `exported_endpoint` under Kubernetes ServiceMonitor scraping
- Tenant reactivation and email-verification workflow, with "Pending Activation" status preserved during deactivation
- Deactivated-tenant login no longer reports the account as suspended
- Correct status codes on invalid identifiers: 422 for a structurally invalid model ID, 400 for an invalid `service_id` format, 404 for a nonexistent `tier_id` or an int4-overflow `tenant_id`
- `WRONGTYPE` Redis errors handled in `cache_service` for legacy string keys
- Trace-pipeline Kafka to OpenSearch deduplication, and missing OpenTelemetry packages pinned
- Anonymous Try It Now feature

### Security
- RBAC matrix enforced for Moderator on pay-per-use endpoints
- `GET /pay-per-use/tenant/tier` protected with the `ppu.tenant.read` permission
- simple-ui decoupled from internal permission IDs in API Key Management

---

## [2.2.0] - 2026-07-03

### Security
- Upgraded Next.js from 14.2.32 to 15.5.19 to remediate CVE (AI4IDS-1864)
- Remediated backend Snyk findings — broke taint chains for SQLi and Open Redirect (AI4IDS-1863)
- Patched transitive `yaml@1.10.2` vulnerability (SNYK-JS-YAML-15765520)
- Fixed DOM XSS in OCR image preview URL handling
- Resolved false-positive hardcoded secret in `apiKeyUtils`
- Applied `postcss` XSS patch via npm override
- SonarQube-driven platform-wide security hardening

---

## [2.1.0] - 2026-06-08

> Hardening release — 60+ PRs merged, 220+ commits

### Added
- Tenant suspension enforcement blocking login and token refresh
- Moderator and tenant-admin permission scoping
- Migration integrity validation via pre-commit hook
- Non-root container security hardening across all service Dockerfiles

### Changed
- Inference service refactored to configuration-driven post-processing
- RBAC boundary enforcement tightened across all endpoints

### Fixed
- Multi-tenancy correctness issues across service boundaries
- Database migration guardrails to prevent accidental schema changes in production

---

## [2.0.0] - 2026-05-31

### Added
- Dedicated **auth-service** — authentication, tenancy flows, JWT issuance and validation
- **platform-core-service** — unified model and alert management, consolidating multiple prior services
- **inference-service** — standardised inference architecture with unified endpoints
- Shared component libraries for cross-service reuse
- Enhanced monitoring across the platform

---

## [1.1.0] - 2026-04-17

> 812 files changed, 60 PRs merged

### Added
- Modular `app/` architecture across all 12 inference services (migrated from flat structure)
- Per-service health validation gating before accepting traffic
- API-key rate limiting and email verification enforcement
- Guest role with session-scoped JWT
- Complete PII type management CRUD with ReDoS protection
- Alembic migration safety: auto-generation blocked in production environments

### Changed
- Duplicated code extracted into shared service factories
- Endpoint validation and service ID generation standardised
- Unified SSL verification across services
- Telemetry standardised with a 7-phase trace lifecycle

---

## [1.0.0] - 2026-03-31

> Auth Service v2 — 276 files changed, 15 microservices updated

### Added
- RS256 asymmetric JWT signing replacing symmetric secrets
- OAuth2 support
- JWT-based API keys
- 66 granular permissions across 16 resource groups
- RBAC powered by Casbin policy engine
- 5 predefined roles: `ADMIN`, `MODERATOR`, `TENANT_ADMIN`, `USER`, `GUEST`
- Multi-tenant user management with tenant status enforcement at login
- PII Guardrail service with language-aware redaction
- Enhanced alerting with history tracking
- Centralised shared libraries for exceptions and bootstrapping

---

## [0.6.0] - 2026-03-17

### Added
- Tenant-level alert routing per alert definition
- Tenant-scoped telemetry visibility
- Tenant Admin and Moderator roles
- Published/unpublished service filtering
- Anonymous NMT access with rate limiting
- API Gateway implementation
- Feature-flagged Home experience

### Changed
- Multi-tenant access control improved across service boundaries

---

## [0.5.0] - 2026-02-25

### Added
- Smart Model Router (SMR) Phase 1 — intelligent model routing across backends
- Alert Management Service — definitions, receivers, and routing rules
- Multi-tenancy v2
- Policy engine with latency, cost, and accuracy policy support
- Docs manager
- Enhanced RBAC with superuser role
- Password management and reset flows
- Client IP capturing and trace correlation in telemetry

---

## [0.4.0] - 2026-02-10

### Added
- A/B testing — Experiment Management with traffic distribution via deterministic hashing
- OpenTelemetry instrumentation across all services
- Real-time logs and traces dashboards (admin-restricted)
- Alert definitions with application and infrastructure categories
- Multi-tenancy v1 — multi-tenant database schema and routing
- Google OAuth integration
- API key management improvements
- Prometheus alerting integration

---

## [0.3.0] - 2026-01-16

### Added
- Request/response logging middleware capturing full request metadata
- Distributed tracing with Jaeger — cross-service trace propagation with correlation IDs
- Jaeger trace URL embedded in log entries
- Model versioning
- Automated API request/response logging

### Fixed
- RBAC permission resolution issues
- API key validation bugs
- Session expiry edge cases

---

[Unreleased]: https://github.com/COSS-India/ai4i-core/compare/v2.5...HEAD
[2.5.0]: https://github.com/COSS-India/ai4i-core/compare/v2.4...v2.5
[2.4.0]: https://github.com/COSS-India/ai4i-core/compare/v2.3...v2.4
[2.3.0]: https://github.com/COSS-India/ai4i-core/compare/v2.2...v2.3
[2.2.0]: https://github.com/COSS-India/ai4i-core/compare/v2.1...v2.2
[2.1.0]: https://github.com/COSS-India/ai4i-core/compare/v2.0...v2.1
[2.0.0]: https://github.com/COSS-India/ai4i-core/compare/v1.1...v2.0
[1.1.0]: https://github.com/COSS-India/ai4i-core/compare/v1.0...v1.1
[1.0.0]: https://github.com/COSS-India/ai4i-core/compare/0.6...v1.0
[0.6.0]: https://github.com/COSS-India/ai4i-core/compare/v0.5...0.6
[0.5.0]: https://github.com/COSS-India/ai4i-core/compare/v0.4...v0.5
[0.4.0]: https://github.com/COSS-India/ai4i-core/compare/v0.3...v0.4
[0.3.0]: https://github.com/COSS-India/ai4i-core/releases/tag/v0.3
