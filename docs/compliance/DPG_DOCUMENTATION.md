# DPG Documentation Summary

This document answers the Digital Public Goods (DPG) certification **Documentation**
requirement for Open Software. It maps each document the DPG Alliance requires to where it
lives in this repository, and it summarizes how and where the AI4I-Core platform is
documented. The documentation is written so a technical person unfamiliar with the solution
can install, run, and operate it themselves.

Reference: [DPG Alliance — 5. Documentation (Open Software)](https://github.com/DPGAlliance/dpg-resources/wiki/5.-Documentation#open-software).
Formats follow [The Good Docs Project (TGDP) templates](https://gitlab.com/tgdp/templates).

Links point to the `release-2.3` branch.

## Summary

AI4I-Core is an open-source, self-hosted platform of three FastAPI microservices (auth,
platform-core, inference) for multilingual language-AI services (translation, speech, OCR,
NER, LLM). Documentation is versioned in this repository and organized to match the seven
DPG-required document types below.

## Required documents (DPG Open Software)

### 1. Overview
Introduces what the software does, how it works, and who it is for.
- [README](https://github.com/COSS-India/ai4i-core/blob/release-2.3/README.md) — "What This Repository Provides", "Who This Project Is For", architecture overview
- [System overview](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/00-overview.md)
- [Codebase guide](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/CODEBASE_GUIDE.md)

### 2. Architectural Diagrams
Shows structure, components, and relationships with visual diagrams and descriptions.
- [Architecture and observability diagrams](https://github.com/COSS-India/ai4i-core/blob/release-2.3/README.md#-architecture-overview) (rendered in the README, mermaid sources under `docs/images/`)
- [System overview](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/00-overview.md)
- Code-anchored per-service architecture: [auth](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/01-auth-service.md) · [platform-core](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/02-platform-core-service.md) · [inference](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/architecture/03-inference-service.md)

### 3. Technology Stack
Lists technologies and dependencies, with versions and compatibility.
- [README — Technology Stack](https://github.com/COSS-India/ai4i-core/blob/release-2.3/README.md#-technology-stack) (FastAPI, Python 3.11, PostgreSQL 15, Redis 7, Next.js 14, and more, with versions)
- [Third-party licenses](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/THIRD_PARTY_LICENSES.md) — every dependency, its version, and its license

### 4. Installation Guide
Explains how to install and run the software in different environments (local and production).
- [README — Deploy Your Own Instance](https://github.com/COSS-India/ai4i-core/blob/release-2.3/README.md#-deploy-your-own-instance) (Install → Configure → Run → Troubleshoot)
- [Setup guide (comprehensive local, Windows/WSL)](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/SETUP_GUIDE.md)
- [End-to-end setup guide](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/END-TO-END-SETUP-GUIDE.md)
- [Single-command setup](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/SINGLE_COMMAND_SETUP.md)
- [Docker Compose local reference](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/DOCKER-COMPOSE-LOCAL-REFERENCE.md)

> **Gap being addressed:** current guides cover local installation thoroughly. A dedicated
> production deployment guide (APISIX gateway, `infrastructure/` configs, production
> environment variables) is being added under a separate ticket.

### 5. User Guide
Teaches end-users how to use the software, and may include an FAQ.
- Live API documentation per service: Swagger UI at `/docs`, ReDoc at `/redoc`, raw spec at `/openapi.json`
- [Simple UI README](https://github.com/COSS-India/ai4i-core/blob/release-2.3/frontend/simple-ui/README.md) — the web interface for exercising the APIs

> **Gap being addressed:** a dedicated end-user User Guide (make an inference call, use the
> Simple UI, manage API keys) with an FAQ is being added under a separate ticket. Scope and
> depth to be confirmed with DPGA experts.

### 6. Release Notes
Follows semantic versioning and documents changes per version.
- [Changelog](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CHANGELOG.md) — per-version history (Keep a Changelog + Semantic Versioning)
- [Release process](https://github.com/COSS-India/ai4i-core/blob/release-2.3/RELEASE.md) — branching, SemVer `MAJOR.MINOR.PATCH`, tagging
- [GitHub Releases](https://github.com/COSS-India/ai4i-core/releases)

### 7. Contributing Guide
Guidelines on contributing and participating in the project.
- [Contributing guidelines](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CONTRIBUTING.md) — how to fork, branch, and open a pull request
- [Code of conduct](https://github.com/COSS-India/ai4i-core/blob/release-2.3/CODE_OF_CONDUCT.md)

## Status against the DPG checklist

| # | Required document | Status |
|---|-------------------|--------|
| 1 | Overview | Complete |
| 2 | Architectural Diagrams | Complete |
| 3 | Technology Stack | Complete |
| 4 | Installation Guide | Local complete; production guide in progress |
| 5 | User Guide | API and UI docs present; dedicated user guide in progress |
| 6 | Release Notes | Complete |
| 7 | Contributing Guide | Complete |

## Additional compliance documents
- [PII data inventory](https://github.com/COSS-India/ai4i-core/blob/release-2.3/docs/compliance/PII_DATA_INVENTORY.md) — data collected/stored, retention, access, protection
- [License: MIT](https://github.com/COSS-India/ai4i-core/blob/release-2.3/LICENSE)

## Pending confirmations
- Functional documents to be reverified by Namrath.
- Placement of documents for submission to be confirmed by Mani.
- User Guide scope to be confirmed by DPGA experts.
