# AI4I-Core Microservices Platform

> **Open-source codebase** for building enterprise-grade AI/ML microservices platforms for Indic languages. Not a hosted service - you deploy and manage it yourself.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Issues](https://img.shields.io/github/issues/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/issues)
[![GitHub Stars](https://img.shields.io/github/stars/COSS-India/ai4i-core)](https://github.com/COSS-India/ai4i-core/stargazers)

---

## 📋 Suggested GitHub "About" Section

**Copy this text for your GitHub repository's About section:**

```
Open-source codebase for AI/ML microservices platform supporting 22+ Indic languages. 
Includes ASR, TTS, NMT, LLM services with FastAPI, Docker, Kong, and observability stack. 
Deploy your own instance - not a hosted service.
```

**Topics to add**: `fastapi` `microservices` `indic-languages` `speech-to-text` `text-to-speech` `machine-translation` `docker` `kubernetes` `kong-gateway` `opentelemetry` `python` `typescript` `nextjs` `ai-ml` `open-source` `self-hosted`

---

## 🎯 What This Repository Provides

An open-source microservices platform codebase built with FastAPI, providing a complete reference implementation for deploying scalable language AI services. This repository contains production-ready code following best practices for microservices architecture, observability, and progressive delivery.

**What You Get**: Complete source code, Docker configurations, deployment manifests, and documentation to build and deploy your own AI/ML platform for Indic languages in your own infrastructure.

## 🏗️ Architecture Overview

<img width="413" height="392" alt="image" src="https://github.com/user-attachments/assets/78400e0a-d180-4c74-9e75-1c15b4b4c8bb" />

This open-source codebase includes **21 microservices**, **1 frontend application**, **15+ infrastructure components**, and **4 shared libraries** that you can deploy in your own environment:

## 📦 What This Repository Provides

This repository contains:
- ✅ **Complete source code** for all microservices and frontend
- ✅ **Docker and Docker Compose** configurations for easy deployment
- ✅ **Infrastructure as Code** - Pre-configured Postgres, Redis, Kafka, Kong, Prometheus, Grafana, etc.
- ✅ **Production-ready examples** - Authentication, rate limiting, observability, feature flags
- ✅ **Comprehensive documentation** - Setup guides, API docs, architecture diagrams
- ✅ **Reusable libraries** - Shared Python modules for logging, observability, model management
- ✅ **Reference implementations** - Best practices for microservices, AI/ML serving, and scalability

**Note**: This is **not a hosted service**. You deploy and manage the platform in your own infrastructure (on-premises, cloud, or hybrid).

## 🎯 Core Services

### Platform Services

- **API Gateway Service** (Port 8080) - Central entry point with routing, rate limiting, and authentication
- **Authentication & Authorization Service** (Port 8081) - Identity management with JWT, OAuth2, and Casbin RBAC | [Documentation](services/auth-service/docs/SERVICE_DOCUMENTATION.md)
- **Configuration Management Service** (Port 8082) - Centralized configuration, feature flags with Unleash, and service registry | [Documentation](services/config-service/docs/SERVICE_DOCUMENTATION.md)
- **Model Management Service** (Port 8094) - Model versioning, lifecycle management, and Triton endpoint registry
- **Multi-Tenant Service** (Port 8100) - Multi-tenancy support with tenant isolation and quota management
- **Metrics Service** (Port 8083) - Metrics collection and aggregation
- **Telemetry Service** (Port 8084) - Distributed tracing and logging aggregation
- **Alerting Service** (Port 8085) - Real-time alerting and notification system
- **Dashboard Service** (Port 8090/8501) - Streamlit-based analytics dashboard

### AI/ML Services

- **ASR Service** (Port 8087) - Speech-to-Text with 22+ Indic languages, WebSocket streaming | [Documentation](services/asr-service/docs/SERVICE_DOCUMENTATION.md)
- **TTS Service** (Port 8088) - Text-to-Speech with multiple voice options, WebSocket streaming | [Documentation](services/tts-service/docs/SERVICE_DOCUMENTATION.md)
- **NMT Service** (Port 8091) - Neural Machine Translation for Indic languages | [Documentation](services/nmt-service/docs/SERVICE_DOCUMENTATION.md)
- **LLM Service** (Port 8093) - Large Language Model service for text generation with streaming | [Documentation](services/llm-service/docs/SERVICE_DOCUMENTATION.md)
- **Pipeline Service** (Port 8092) - Orchestrates multiple AI services in workflows | [Documentation](services/pipeline-service/docs/SERVICE_DOCUMENTATION.md)
- **OCR Service** (Port 8099) - Optical Character Recognition for Indic scripts
- **NER Service** (Port 9001) - Named Entity Recognition for Indic languages
- **Transliteration Service** (Port 8097) - Script transliteration between Indic languages
- **Language Detection Service** (Port 8098) - Text-based language identification
- **Audio Language Detection Service** (Port 8096) - Audio-based language identification
- **Speaker Diarization Service** (Port 8095) - Speaker identification and segmentation
- **Language Diarization Service** (Port 9002) - Multi-lingual audio segmentation

## 🎨 Frontend

- **Simple UI Frontend** (Port 3000) - Modern web interface built with Next.js 13, Chakra UI, and TypeScript for testing all AI services

## 🔧 Infrastructure Components

### Data Storage

- **PostgreSQL** (Port 5434) - Primary relational database with separate schemas for each service
- **PostgreSQL-Konga** (Port 5435) - Dedicated PostgreSQL instance for Konga (Kong admin UI)
- **Redis** (Port 6381) - In-memory data store for caching, session management, and rate limiting
- **InfluxDB** (Port 8089) - Time-series database for metrics storage

### API Management

- **Kong Gateway** (Port 8000/8443) - Enterprise API Gateway with custom plugins for token validation
- **Konga** (Port 8002) - Web-based Kong administration UI
- **Swagger UI** (Port 8086) - Interactive API documentation viewer for Kong-facing APIs

### Observability & Monitoring

- **Prometheus** (Port 9090) - Metrics collection and time-series database
- **Grafana** (Port 3001) - Metrics visualization and dashboards with pre-configured DevOps operational dashboard
- **Node Exporter** (Port 9100) - System-level metrics exporter for Prometheus
- **OpenSearch** (Port 9204) - Distributed search and analytics engine for logs
- **OpenSearch Dashboards** (Port 5602) - Log visualization and analysis interface
- **Jaeger** (Port 16686) - Distributed tracing with OpenTelemetry support
- **Fluent Bit** - Log collection and forwarding agent

### Event Streaming

- **Kafka** (Port 9093) - Event streaming platform for real-time data pipelines
- **Zookeeper** (Port 2181) - Distributed coordination service for Kafka

### Feature Management

- **Unleash** (Port 4242) - Feature flag management and progressive delivery with OpenFeature SDK integration

## 📚 Shared Libraries

The platform includes reusable Python libraries for common functionality:

- **ai4icore_logging** - Structured logging with context propagation
- **ai4icore_observability** - OpenTelemetry instrumentation and metrics
- **ai4icore_telemetry** - Distributed tracing utilities
- **ai4icore_model_management** - Model Management Service client, Triton client wrapper, and caching

## ✨ Features Included in This Codebase

### AI/ML Service Code
- **22+ Indic Languages Support** - Complete implementation for Indian languages in ASR, TTS, and NMT
- **Real-time Streaming** - WebSocket-based streaming implementation for ASR and TTS with low latency
- **Multi-Service Pipelines** - Code to chain multiple AI services (ASR → NMT → TTS) for complex workflows
- **Model Versioning** - Complete model lifecycle management system with versioning and registry
- **Triton Integration** - Production-ready integration with NVIDIA Triton Inference Server

### Platform Code & Infrastructure
- **Feature Flags** - Integrated Unleash + OpenFeature implementation for progressive delivery
- **Multi-Tenancy** - Complete multi-tenant architecture with tenant isolation and quota management
- **API Gateway** - Kong-based API management with custom plugins for token validation
- **Authentication & Authorization** - Full JWT, OAuth2, and Casbin RBAC implementation
- **Distributed Tracing** - OpenTelemetry instrumentation with Jaeger integration
- **Centralized Logging** - Fluent Bit, OpenSearch, and OpenSearch Dashboards setup
- **Metrics & Monitoring** - Prometheus, Grafana dashboards, and InfluxDB configuration
- **Horizontal Scaling** - Stateless service design ready for Docker Swarm or Kubernetes
- **Service Registry** - Dynamic service discovery and health monitoring implementation

### Developer Tools & Experience
- **Modern Web UI Code** - Complete Next.js 13 frontend with TypeScript, Chakra UI, and TanStack React Query
- **Interactive Testing Interface** - UI for testing all AI services with microphone recording, file upload, and visualization
- **API Documentation** - Auto-generated Swagger/OpenAPI documentation for all service endpoints
- **Docker Compose** - Production-ready Docker Compose files for single-command deployment
- **Kubernetes Manifests** - K8s migration guides and deployment configurations
- **Shared Libraries** - Reusable Python modules for logging, observability, and model management

## 🛠️ Technology Stack

### Backend
- **FastAPI** - High-performance async Python web framework
- **PostgreSQL 15** - ACID-compliant relational database
- **Redis 7** - In-memory data store for caching and rate limiting
- **SQLAlchemy** - Async ORM with connection pooling
- **Pydantic** - Data validation and serialization
- **NVIDIA Triton** - ML model serving infrastructure

### Frontend
- **Next.js 13.1.1** - React framework with App Router
- **TypeScript** - Type-safe JavaScript
- **Chakra UI** - Component library for accessible UI
- **TanStack React Query** - Server state management
- **Socket.IO Client** - WebSocket communication

### Infrastructure
- **Docker & Docker Compose** - Containerization and orchestration
- **Kong 3.4** - API Gateway with Lua plugins
- **Prometheus & Grafana** - Monitoring and visualization
- **OpenSearch & Jaeger** - Logging and tracing
- **Kafka & Zookeeper** - Event streaming
- **Unleash** - Feature flag management

## 🚀 Deploy Your Own Instance

This repository provides all the code and configurations you need to deploy your own AI4I-Core platform.

### Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- 16GB+ RAM recommended (for running all services locally)
- 50GB+ disk space for all services and databases
- Linux/macOS (Windows with WSL2)
- Your own Triton Inference Server or compatible model serving endpoint (for AI/ML services)

### Quick Start (Local Deployment)

```bash
# 1. Clone this repository
git clone https://github.com/COSS-India/ai4i-core.git
cd ai4i-core

# 2. Copy environment template
cp env.template .env

# 3. Configure your environment variables
nano .env
# Update database credentials, API keys, Triton endpoints, etc.

# 4. Start all services using Docker Compose
docker-compose up -d

# 5. Check service health
docker-compose ps

# 6. Access your deployed instance
open http://localhost:3000
```

### Service URLs (After Deployment)

Once deployed locally, access your services at:

- **Frontend UI**: http://localhost:3000
- **API Gateway**: http://localhost:8080
- **Kong Admin**: http://localhost:8001
- **Konga UI**: http://localhost:8002
- **Grafana**: http://localhost:3001
- **Prometheus**: http://localhost:9090
- **OpenSearch Dashboards**: http://localhost:5602
- **Jaeger UI**: http://localhost:16686
- **Unleash**: http://localhost:4242

> **Note**: These URLs are for local deployment. For production deployments on your infrastructure, configure domain names and SSL certificates as per [DEPLOYMENT.md](docs/DEPLOYMENT.md).

## 📖 Documentation

### Setup & Deployment
- [Setup Guide](docs/SETUP_GUIDE.md) - Comprehensive setup instructions
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment guide
- [Architecture](docs/ARCHITECTURE.md) - Detailed architecture documentation
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

### Migration Guides
- [Kubernetes Migration](K8s-MIGRATION-GUIDE.md) - Migrate from Docker Compose to Kubernetes
- [Docker Swarm Migration](SWARM-MIGRATION-GUIDE.md) - Migrate to Docker Swarm
- [Container Platform Comparison](CONTAINER-PLATFORM-COMPARISON.md) - Compare deployment options

### Service Documentation
- [Auth Service](services/auth-service/docs/SERVICE_DOCUMENTATION.md)
- [Config Service](services/config-service/docs/SERVICE_DOCUMENTATION.md)
- [ASR Service](services/asr-service/docs/SERVICE_DOCUMENTATION.md)
- [TTS Service](services/tts-service/docs/SERVICE_DOCUMENTATION.md)
- [NMT Service](services/nmt-service/docs/SERVICE_DOCUMENTATION.md)
- [LLM Service](services/llm-service/docs/SERVICE_DOCUMENTATION.md)
- [Pipeline Service](services/pipeline-service/docs/SERVICE_DOCUMENTATION.md)

### Additional Resources
- [API Documentation](docs/API_DOCUMENTATION.md)
- [Model Management Integration Guide](docs/MODEL_MANAGEMENT_INTEGRATION_GUIDE.md)
- [Microservice Implementation Prompt](MICROSERVICE_IMPLEMENTATION_PROMPT.md)

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our coding standards
4. Add tests for new functionality
5. Update documentation as needed
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## 🔌 Port Reference

### Platform Services
| Service | Port | Description |
|---------|------|-------------|
| API Gateway | 8080 | Main API entry point |
| Auth Service | 8081 | Authentication & Authorization |
| Config Service | 8082 | Configuration Management |
| Metrics Service | 8083 | Metrics Collection |
| Telemetry Service | 8084 | Distributed Tracing |
| Alerting Service | 8085 | Alerting & Notifications |
| Dashboard Service | 8090, 8501 | Analytics Dashboard |

### AI/ML Services
| Service | Port | Description |
|---------|------|-------------|
| ASR Service | 8087 | Speech-to-Text |
| TTS Service | 8088 | Text-to-Speech |
| NMT Service | 8091 | Neural Machine Translation |
| Pipeline Service | 8092 | Service Orchestration |
| LLM Service | 8093 | Large Language Models |
| Model Management | 8094 | Model Lifecycle Management |
| Speaker Diarization | 8095 | Speaker Identification |
| Audio Language Detection | 8096 | Audio Language ID |
| Transliteration | 8097 | Script Transliteration |
| Language Detection | 8098 | Text Language ID |
| OCR Service | 8099 | Optical Character Recognition |
| Multi-Tenant Service | 8100 | Multi-tenancy Management |
| NER Service | 9001 | Named Entity Recognition |
| Language Diarization | 9002 | Multi-lingual Segmentation |

### Frontend & API Management
| Service | Port | Description |
|---------|------|-------------|
| Simple UI | 3000 | Web Interface |
| Kong Gateway | 8000, 8443 | API Gateway (HTTP/HTTPS) |
| Kong Admin | 8001 | Kong Admin API |
| Konga UI | 8002 | Kong Management UI |
| Swagger UI | 8086 | API Documentation |

### Infrastructure
| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5434 | Primary Database |
| PostgreSQL-Konga | 5435 | Konga Database |
| Redis | 6381 | Cache & Session Store |
| InfluxDB | 8089 | Time-series Metrics |
| Kafka | 9093 | Event Streaming |
| Zookeeper | 2181 | Kafka Coordination |
| Unleash | 4242 | Feature Flags |

### Observability
| Service | Port | Description |
|---------|------|-------------|
| Grafana | 3001 | Metrics Visualization |
| Prometheus | 9090 | Metrics Collection |
| Node Exporter | 9100 | System Metrics |
| Elasticsearch | 9203 | Log Storage (Legacy) |
| OpenSearch | 9204, 9600 | Log Storage & Search |
| OpenSearch Dashboards | 5602 | Log Visualization |
| Jaeger UI | 16686 | Distributed Tracing |
| Jaeger Collector | 14268 | Trace Collection (HTTP) |
| Jaeger Agent | 6831 | Trace Collection (UDP) |
| OTLP gRPC | 4317 | OpenTelemetry Protocol |
| OTLP HTTP | 4318 | OpenTelemetry Protocol |

## 📊 Monitoring & Observability

The platform includes comprehensive monitoring with pre-configured dashboards:

- **Grafana Dashboard**: DevOps Operational Dashboard with service health, resource utilization, and performance metrics
- **Prometheus Metrics**: Service-level metrics, request rates, error rates, and latency
- **OpenSearch Logs**: Centralized logging with structured logs and context propagation
- **Jaeger Tracing**: Distributed tracing with service dependency mapping

## 🏗️ Architecture Highlights

- **Microservices Architecture**: 21 independent, scalable services
- **API-First Design**: OpenAPI/Swagger documentation for all endpoints
- **Event-Driven**: Kafka-based event streaming for decoupled services
- **Multi-Layer Caching**: In-memory + Redis for optimal performance
- **Repository Pattern**: Clean separation of data access layer
- **Dependency Injection**: FastAPI Depends() for loose coupling
- **Middleware Pipeline**: Reusable cross-cutting concerns (auth, logging, rate limiting)
- **Feature Flags**: Progressive delivery with targeting and gradual rollouts
- **Health Checks**: Comprehensive health monitoring with dependency tracking

## ⚠️ Important Disclaimers

### What This Repository Is
- ✅ **Open-source codebase** - Complete source code for building your own AI/ML platform
- ✅ **Reference architecture** - Production-ready implementation you can learn from and customize
- ✅ **Self-hosted solution** - Deploy and manage in your own infrastructure
- ✅ **Community-supported** - Open-source project with community contributions

### What This Repository Is NOT
- ❌ **Not a hosted/managed service** - You must deploy and maintain it yourself
- ❌ **Not a SaaS platform** - No cloud service or API endpoints provided by us
- ❌ **Not commercially supported** - No SLA, guaranteed uptime, or paid support plans
- ❌ **Not plug-and-play** - Requires infrastructure, DevOps knowledge, and ML model access

### Your Responsibilities When Using This Code
- Deploying and maintaining the infrastructure (servers, databases, networking)
- Securing your deployment (SSL, firewalls, secrets management)
- Providing your own ML models or Triton Inference Server endpoints
- Monitoring, logging, and incident response for your deployment
- Compliance with data privacy and security regulations in your jurisdiction
- Managing costs for your cloud/on-premises infrastructure

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

**MIT License means**: You are free to use, modify, and distribute this code, including for commercial purposes, but with no warranty or liability from the maintainers.

## 💬 Community & Support

This is an **open-source project**. Community support is available through:

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/COSS-India/ai4i-core/issues)
- **Documentation**: Check the [docs](docs/) directory for setup guides, API documentation, and architecture details
- **Troubleshooting**: Review [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common deployment issues
- **Discussions**: Join discussions for questions and community help
- **Pull Requests**: Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

For deployment issues:
- **Logs**: Use `docker-compose logs <service-name>` to review service logs in your deployment
- **Health Checks**: Visit `http://localhost:<port>/health` for any service in your environment

> **Note**: This is open-source code provided as-is. There is no commercial support or SLA. For enterprise support options, you may need to engage third-party service providers or build your own support team.

## 🙏 Acknowledgments

Built with cutting-edge open-source technologies:
- FastAPI, PostgreSQL, Redis, Kafka
- Kong Gateway, Unleash, OpenFeature
- Prometheus, Grafana, Jaeger, OpenSearch
- Next.js, React, TypeScript, Chakra UI
- NVIDIA Triton Inference Server

---

**Note**: For production deployments, refer to [DEPLOYMENT.md](docs/DEPLOYMENT.md) for security hardening, scaling strategies, and best practices.
