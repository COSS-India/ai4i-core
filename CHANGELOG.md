# Changelog

All notable changes to AI4I-Core are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).


## [2.2.0] - 2026-06-08

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

[Unreleased]: https://github.com/COSS-India/ai4i-core/compare/v2.1...HEAD
[2.2.0]: https://github.com/COSS-India/ai4i-core/compare/v2.1...HEAD
[2.1.0]: https://github.com/COSS-India/ai4i-core/compare/v2.0...v2.1
[2.0.0]: https://github.com/COSS-India/ai4i-core/compare/v1.1...v2.0
[1.1.0]: https://github.com/COSS-India/ai4i-core/compare/v1.0...v1.1
[1.0.0]: https://github.com/COSS-India/ai4i-core/compare/0.6...v1.0
[0.6.0]: https://github.com/COSS-India/ai4i-core/compare/v0.5...0.6
[0.5.0]: https://github.com/COSS-India/ai4i-core/compare/v0.4...v0.5
[0.4.0]: https://github.com/COSS-India/ai4i-core/compare/v0.3...v0.4
[0.3.0]: https://github.com/COSS-India/ai4i-core/releases/tag/v0.3
