# AI4I-Core Microservices Platform.

A comprehensive microservices platform built with FastAPI, following the AI4I-Core Platform's Frontend-Backend Communication Flow pattern. The platform provides the capabilities to scale up the language AI models to a high degree.

## 🏗️ Architecture Overview

<img width="413" height="392" alt="image" src="https://github.com/user-attachments/assets/78400e0a-d180-4c74-9e75-1c15b4b4c8bb" />

The current version of platform consists of 12 microservices, 1 frontend application, and 7 infrastructure components:

### Microservices

- **API Gateway Service** (Port 8080) - Central entry point with routing, rate limiting, and authentication
- **Authentication & Authorization Service** (Port 8081) - Identity management with JWT and OAuth2 | [Documentation](services/auth-service/docs/SERVICE_DOCUMENTATION.md)
- **Configuration Management Service** (Port 8082) - Centralized configuration, feature flags with Unleash, and service registry | [Documentation](services/config-service/docs/SERVICE_DOCUMENTATION.md)
- **ASR Service** (Port 8087) - Speech-to-Text with 22+ Indic languages | [Documentation](services/asr-service/docs/SERVICE_DOCUMENTATION.md)
- **TTS Service** (Port 8088) - Text-to-Speech with multiple voice options | [Documentation](services/tts-service/docs/SERVICE_DOCUMENTATION.md)
- **NMT Service** (Port 8091) - Neural Machine Translation for Indic languages | [Documentation](services/nmt-service/docs/SERVICE_DOCUMENTATION.md)
- **LLM Service** (Port 8093) - Large Language Model service for text generation | [Documentation](services/llm-service/docs/SERVICE_DOCUMENTATION.md)
- **Pipeline Service** (Port 8092) - Orchestrates multiple AI services in workflows | [Documentation](services/pipeline-service/docs/SERVICE_DOCUMENTATION.md)

### Frontend

- **Simple UI Frontend** (Port 3000) - Web interface for testing AI services

### Infrastructure Components

- **PostgreSQL** (Port 5434) - Primary database with separate schemas for each service
- **Redis** (Port 6381) - Caching, session management, and rate limiting
- **InfluxDB** (Port 8089) - Time-series database for metrics storage
- **Elasticsearch** (Port 9203) - Log storage and search engine
- **Kafka** (Port 9093) - Event streaming and message queuing
- **Zookeeper** (Port 2181) - Kafka coordination service
- **Unleash** (Port 4242) - Feature flag management and progressive delivery (uses shared PostgreSQL)

**Features**:

- Feature flags with Unleash and OpenFeature for progressive delivery
- Boolean, variant, and gradual rollout support
- Modern, responsive web interface built with Next.js 13 and Chakra UI
- ASR testing with microphone recording and file upload
- TTS testing with text input and voice selection
- NMT testing with language pair selection
- Real-time WebSocket streaming for ASR and TTS
- API key management
- Request/response visualization with stats
- Audio waveform visualization

**Technology Stack**: Next.js 13.1.1, TypeScript, Chakra UI, TanStack React Query, Socket.IO Client, Framer Motion

## 🚀 Getting Started

For setup instructions, refer to the [Setup Guide](docs/SETUP_GUIDE.md) or the wiki section for detailed setup instructions.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🤝 Support

For support and questions:

- Create an issue in the repository
- Check the troubleshooting section
- Review the logs for error details
