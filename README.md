# AI4I-Core Microservices Platform.

A comprehensive microservices platform built with FastAPI, following the AI4I-Core Platform's Frontend-Backend Communication Flow pattern. The platform provides the capabilities to scale up the language AI models to a high degree.

## 🏗️ Architecture Overview

<img width="413" height="392" alt="image" src="https://github.com/user-attachments/assets/78400e0a-d180-4c74-9e75-1c15b4b4c8bb" />

The current version of platform consists of 10 microservices, 1 frontend application, and 5 infrastructure components:

### Microservices

- **API Gateway Service** (Port 8080) - Central entry point with routing, rate limiting, and authentication
- **Authentication & Authorization Service** (Port 8081) - Identity management with JWT and OAuth2
- **Configuration Management Service** (Port 8082) - Centralized configuration and feature flags
- **Metrics Collection Service** (Port 8083) - System and application metrics collection
- **Telemetry Service** (Port 8084) - Log aggregation, distributed tracing, and event correlation
- **Alerting Service** (Port 8085) - Proactive issue detection and notification
- **Dashboard Service** (Port 8086) - Visualization and reporting with Streamlit UI (Port 8501)
- **ASR Service** (Port 8087) - Speech-to-Text with 22+ Indic languages
- **TTS Service** (Port 8088) - Text-to-Speech with multiple voice options
- **NMT Service** (Port 8089) - Neural Machine Translation for Indic languages

### Frontend

- **Simple UI Frontend** (Port 3000) - Web interface for testing AI services

### Infrastructure Components

- **PostgreSQL** (Port 5432) - Primary database with separate schemas for each service
- **Redis** (Port 6379) - Caching, session management, and rate limiting
- **InfluxDB** (Port 8086) - Time-series database for metrics storage
- **Elasticsearch** (Port 9200) - Log storage and search engine
- **Kafka** (Port 9092) - Event streaming and message queuing
- **Zookeeper** (Port 2181) - Kafka coordination service

**Features**:

- Modern, responsive web interface built with Next.js 13 and Chakra UI
- ASR testing with microphone recording and file upload
- TTS testing with text input and voice selection
- NMT testing with language pair selection
- Real-time WebSocket streaming for ASR and TTS
- API key management
- Request/response visualization with stats
- Audio waveform visualization

**Technology Stack**: Next.js 13, TypeScript, Chakra UI, TanStack React Query, Socket.IO Client

Refer to the wiki section for the detailed setup instructions.

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Support

For support and questions:

- Create an issue in the repository
- Check the troubleshooting section
- Review the logs for error details
