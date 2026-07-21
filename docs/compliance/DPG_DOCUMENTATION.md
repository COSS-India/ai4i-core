# DPG Documentation Summary

This document answers the Digital Public Goods (DPG) certification **Documentation**
requirement: a summary of how and where the AI4I-Core platform is documented, with links to
all relevant documents. The documentation is written so a technical person unfamiliar with
the solution can launch and run it themselves.

## Summary

AI4I-Core is an open-source, self-hosted platform of three FastAPI microservices (auth,
platform-core, inference) for multilingual language-AI services. It is documented at four
levels, all versioned in this repository:

1. **Repository README** — architecture overview, service map, technology stack, and a
   quick-start (Install → Configure → Run → Troubleshoot) for standing up a local instance.
2. **Setup and deployment guides** — step-by-step local, end-to-end, single-command, and
   Windows/WSL instructions, plus a Docker Compose reference and a local
   tracing/observability setup guide.
3. **Architecture documentation** — a system overview plus one code-anchored document per
   service, where every non-obvious claim links to a source path. Per-service READMEs and
   design (ARCHITECTURE) documents give deeper detail.
4. **API documentation** — each service auto-generates and serves a live OpenAPI 3.x spec at
   runtime: Swagger UI at `/docs`, ReDoc at `/redoc`, and the raw spec at `/openapi.json`.
   There are no static spec files to maintain.

Compliance and licensing are documented separately: a PII data inventory and a full
third-party license list. Contribution, code of conduct, release process, and changelog
round out the project documentation. The license is MIT.

## Documentation index

Links point to the `release-2.3` branch.

### README and overview
- [README](https://github.com/COSS-India/ai4i-core/blob/release-2.3/README.md) — architecture overview, service map, tech stack, quick start, service URLs, troubleshooting
- [System overview](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/00-overview.md)
- [Codebase guide](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/CODEBASE_GUIDE.md)

### Setup and deployment
- [Setup guide (comprehensive local, Windows/WSL)](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/SETUP_GUIDE.md)
- [End-to-end setup guide](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/END-TO-END-SETUP-GUIDE.md)
- [Single-command setup](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/SINGLE_COMMAND_SETUP.md)
- [Docker Compose local reference](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/DOCKER-COMPOSE-LOCAL-REFERENCE.md)
- [Tracing & observability (local)](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/TRACING-OBSERVABILITY-LOCAL-SETUP.md)

### Architecture (code-anchored)
- [auth-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/01-auth-service.md)
- [platform-core-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/02-platform-core-service.md)
- [inference-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/03-inference-service.md)

### API documentation (OpenAPI 3.x, live)
Each FastAPI service auto-generates and serves its spec at runtime:
- Swagger UI at `/docs`, ReDoc at `/redoc`, raw spec at `/openapi.json`
- All inference capabilities (NMT, ASR, TTS, NER, OCR, transliteration, language/audio-language detection, speaker/language diarization) share one endpoint `POST /api/v1/inference`, routed by `task_type`, with per-task aliases (e.g. `/api/v1/nmt/inference`). LLM chat uses an OpenAI-compatible `POST /api/v1/chat/completions`. Live task list: `GET /api/v1/inference/tasks`.

### Per-service READMEs
- [auth-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/auth-service/README.md)
- [platform-core-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/platform-core-service/README.md)
- [inference-service](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/inference-service/README.md) ([design](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/inference-service/ARCHITECTURE.md))
- [kafka-consumers](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/kafka-consumers/README.md) ([design](https://github.com/COSS-India/ai4i-core/blob/release-2.3/services/kafka-consumers/ARCHITECTURE.md))

### Compliance and licensing
- [PII data inventory](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/compliance/PII_DATA_INVENTORY.md) — data collected/stored, retention, access, protection
- [Third-party licenses](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/THIRD_PARTY_LICENSES.md) — all dependencies, versions, licenses

### Project process
- [Contributing guidelines](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CONTRIBUTING.md)
- [Code of conduct](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CODE_OF_CONDUCT.md)
- [Release process](https://github.com/COSS-India/ai4i-core/blob/release-2.3/RELEASE.md)
- [Changelog](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CHANGELOG.md)
- [License: MIT](https://github.com/COSS-India/ai4i-core/blob/release-2.3/LICENSE)
