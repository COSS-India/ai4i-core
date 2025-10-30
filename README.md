# AI4I-Core Microservices Platform.

A comprehensive microservices platform built with FastAPI, following the AI4I-Core Platform's Frontend-Backend Communication Flow pattern. This platform implements a 6-step communication process with enterprise-grade API services and capabilities.

## 🏗️ Architecture Overview

The platform consists of 10 microservices, 1 frontend application, and 5 infrastructure components:

### Microservices
- **API Gateway Service** (Port 8080) - Central entry point with routing, rate limiting, and authentication
- **Authentication & Authorization Service** (Port 8081) - Identity management with JWT and OAuth2
- **Configuration Management Service** (Port 8082) - Centralized configuration and feature flags
- **Metrics Collection Service** (Port 8083) - System and application metrics collection
- **Telemetry Service** (Port 8084) - Log aggregation, distributed tracing, and event correlation
- **Alerting Service** (Port 8085) - Proactive issue detection and notification
- **Dashboard Service** (Port 8086) - Visualization and reporting with Streamlit UI (Port 8501)
- **ASR Service** (Port 8087) - Speech-to-Text with 22+ Indian languages
- **TTS Service** (Port 8088) - Text-to-Speech with multiple voice options
- **NMT Service** (Port 8089) - Neural Machine Translation for Indian languages

### Frontend
- **Simple UI Frontend** (Port 3000) - Web interface for testing AI services

### Infrastructure Components
- **PostgreSQL** (Port 5432) - Primary database with separate schemas for each service
- **Redis** (Port 6379) - Caching, session management, and rate limiting
- **InfluxDB** (Port 8086) - Time-series database for metrics storage
- **Elasticsearch** (Port 9200) - Log storage and search engine
- **Kafka** (Port 9092) - Event streaming and message queuing
- **Zookeeper** (Port 2181) - Kafka coordination service

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 8GB RAM minimum
- 20GB disk space

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd AI4I-Core-microservices
   ```

2. **Set up environment variables**
   ```bash
   cp env.template .env
   # Edit .env with your configuration values
   ```

3. **Start all services**
   ```bash
   ./scripts/start-all.sh
   ```

4. **Verify installation**
   ```bash
   ./scripts/health-check-all.sh
   ```

## 📊 Service URLs

Once running, access the services at:

- **API Gateway**: http://localhost:8080
- **Auth Service**: http://localhost:8081
- **Config Service**: http://localhost:8082
- **Metrics Service**: http://localhost:8083
- **Telemetry Service**: http://localhost:8084
- **Alerting Service**: http://localhost:8085
- **Dashboard Service**: http://localhost:8086
- **ASR Service**: http://localhost:8087
- **TTS Service**: http://localhost:8088
- **NMT Service**: http://localhost:8089
- **Simple UI**: http://localhost:3000
- **Streamlit Dashboard**: http://localhost:8501

### API Documentation (Swagger UI)
- **ASR Service**: http://localhost:8087/docs
- **TTS Service**: http://localhost:8088/docs
- **NMT Service**: http://localhost:8089/docs
- **API Gateway**: http://localhost:8080/docs

### Infrastructure
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **InfluxDB**: http://localhost:8086
- **Elasticsearch**: http://localhost:9200
- **Kafka**: localhost:9092

## 🤖 AI/ML Services

### ASR Service (Automatic Speech Recognition)
**Port**: 8087

**Capabilities**:
- Speech-to-text conversion for 22+ Indian languages
- Real-time streaming ASR via WebSocket
- Batch processing with multiple audio inputs
- Audio format support: WAV, MP3, FLAC, OGG
- Voice Activity Detection (VAD)
- Inverse Text Normalization (ITN) and punctuation restoration

**Endpoints**:
- `POST /api/v1/asr/inference` - Batch inference
- `WebSocket /socket.io/asr` - Streaming inference
- `GET /api/v1/asr/models` - List available models
- `GET /api/v1/asr/health` - Health check

**Supported Languages**: English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Oriya, Assamese, Urdu, Sanskrit, and more

### TTS Service (Text-to-Speech)
**Port**: 8088

**Capabilities**:
- Text-to-speech conversion for 22+ Indian languages
- Multiple voice options (male/female)
- Real-time streaming TTS via WebSocket
- Audio format output: WAV, MP3, OGG
- Audio duration adjustment
- Voice catalog with 6 pre-configured voices

**Endpoints**:
- `POST /api/v1/tts/inference` - Batch inference
- `WebSocket /socket.io/tts` - Streaming inference
- `GET /api/v1/tts/voices` - List available voices
- `GET /api/v1/tts/health` - Health check

**Voice Models**: Dravidian (Kannada, Malayalam, Tamil, Telugu), Indo-Aryan (Hindi, Bengali, Gujarati, Marathi, Punjabi), Miscellaneous (English, Bodo, Manipuri)

### NMT Service (Neural Machine Translation)
**Port**: 8089

**Capabilities**:
- Neural machine translation for 22+ Indian languages
- Bidirectional translation (any language pair)
- Batch processing (max 90 texts per request)
- Script code support (Devanagari, Arabic, Tamil, etc.)
- Language detection and confidence scoring

**Endpoints**:
- `POST /api/v1/nmt/inference` - Batch inference
- `GET /api/v1/nmt/models` - List available models and language pairs
- `GET /api/v1/nmt/health` - Health check

**Supported Language Pairs**: 400+ combinations including English↔Hindi, English↔Tamil, Hindi↔Tamil, and more

### Simple UI Frontend
**Port**: 3000

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

## 🛠️ Management Scripts

The platform includes several utility scripts for easy management:

### Start/Stop Services
```bash
# Start all services
./scripts/start-all.sh

# Stop all services
./scripts/stop-all.sh

# Stop and remove volumes (clean restart)
./scripts/stop-all.sh --volumes
```

### Service Management
```bash
# Restart a specific service
./scripts/restart-service.sh api-gateway-service

# Restart with rebuild
./scripts/restart-service.sh auth-service --build
```

### Monitoring
```bash
# View logs for all services
./scripts/logs.sh

# View logs for specific service
./scripts/logs.sh api-gateway-service

# Follow logs in real-time
./scripts/logs.sh -f metrics-service

# Check health status
./scripts/health-check-all.sh
```

### Infrastructure
```bash
# Initialize infrastructure (run after first start)
./scripts/init-infrastructure.sh
```

## 🔧 Configuration

### Environment Variables

The platform uses environment variables for configuration. Copy `env.template` to `.env` and customize:

```bash
# Global Configuration
COMPOSE_PROJECT_NAME=AI4I-Core-microservices
ENVIRONMENT=development

# Database Configuration
POSTGRES_USER=AI4I-Core_user
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=AI4I-Core_platform

# Redis Configuration
REDIS_PASSWORD=your_redis_password

# JWT Configuration
JWT_SECRET_KEY=your_jwt_secret_key
JWT_REFRESH_SECRET_KEY=your_refresh_secret_key

# Service URLs
API_GATEWAY_URL=http://api-gateway-service:8080
# ... (see env.template for complete list)
```

### Service-Specific Configuration

Each microservice has its own environment file in `services/<service-name>/env.template`:

- `services/api-gateway-service/env.template`
- `services/auth-service/env.template`
- `services/config-service/env.template`
- `services/metrics-service/env.template`
- `services/telemetry-service/env.template`
- `services/alerting-service/env.template`
- `services/dashboard-service/env.template`
- `services/asr-service/env.template`
- `services/tts-service/env.template`
- `services/nmt-service/env.template`
- `frontend/simple-ui/.env.template`

## 🏥 Health Checks

All services include comprehensive health checks:

- **HTTP Health Endpoints**: Each service exposes `/health` endpoint
- **Docker Health Checks**: Built-in container health monitoring
- **Dependency Checks**: Services verify connectivity to their dependencies
- **Automated Monitoring**: Health check script monitors all services

## 🔒 Security

### Authentication & Authorization
- JWT tokens with configurable expiration
- OAuth2 provider integration (Google, GitHub, Microsoft)
- Role-based access control (RBAC)
- API key management
- Session management with Redis

### Data Protection
- Input validation and sanitization
- SQL injection prevention
- XSS protection
- CSRF protection
- Data encryption at rest and in transit

### Network Security
- Service isolation with Docker networks
- Rate limiting per user and IP
- CORS configuration
- Trusted host middleware

## 📈 Monitoring & Observability

### Metrics Collection
- API usage metrics (request count, response time, error rate)
- System performance metrics (CPU, memory, disk I/O)
- Custom business metrics
- Real-time data streaming

### Logging
- Structured JSON logging
- Centralized log aggregation with Elasticsearch
- Request tracing with correlation IDs
- Error logging with stack traces

### Alerting
- Machine learning-based anomaly detection
- Threshold-based alerting
- Multi-channel notifications (email, Slack, SMS)
- Alert escalation policies

### Dashboards
- Real-time metrics visualization
- Interactive charts and graphs
- Customizable dashboard layouts
- Executive reporting

## 🚀 Deployment

### Development
```bash
# Start with hot-reloading (uses docker-compose.override.yml)
docker-compose up -d

# View logs
docker-compose logs -f
```

### Production
```bash
# Build and start
docker-compose up -d --build

# Scale services
docker-compose up -d --scale api-gateway-service=3
```

### Kubernetes (Future)
- Kubernetes deployment manifests
- Service mesh integration (Istio)
- Horizontal Pod Autoscaling (HPA)
- ConfigMaps and Secrets management

## 🧪 Testing

### Running Tests

**Install Test Dependencies**:
```bash
cd tests
pip install -r requirements.txt
```

**Run All Tests**:
```bash
pytest
```

**Run Integration Tests**:
```bash
pytest -m integration
```

**Run Specific Service Tests**:
```bash
pytest tests/integration/test_asr_service.py
pytest tests/integration/test_tts_service.py
pytest tests/integration/test_nmt_service.py
```

**Run WebSocket Streaming Tests**:
```bash
pytest -m streaming
```

**Run E2E Tests**:
```bash
pytest -m e2e
```

**Generate Coverage Report**:
```bash
pytest --cov=services --cov-report=html
open htmlcov/index.html
```

### Frontend Tests

**Run Frontend Tests**:
```bash
cd frontend/simple-ui
npm test
```

**Run with Coverage**:
```bash
npm test -- --coverage
```

### Test Categories

- **Unit Tests**: Test individual functions/classes in isolation
- **Integration Tests**: Test service endpoints with real dependencies
- **E2E Tests**: Test complete user workflows with browser automation
- **Performance Tests**: Test response times and throughput

## 🔧 Troubleshooting

### Common Issues

1. **Services not starting**
   ```bash
   # Check logs
   ./scripts/logs.sh
   
   # Check health
   ./scripts/health-check-all.sh
   ```

2. **Database connection issues**
   ```bash
   # Check PostgreSQL
   docker-compose exec postgres pg_isready -U AI4I-Core_user
   
   # Check Redis
   docker-compose exec redis redis-cli ping
   ```

3. **Port conflicts**
   ```bash
   # Check port usage
   netstat -tulpn | grep :8080
   
   # Stop conflicting services
   sudo systemctl stop apache2  # if using port 80
   ```

### Logs and Debugging

```bash
# View all logs
./scripts/logs.sh

# View specific service logs
./scripts/logs.sh api-gateway-service

# Follow logs in real-time
./scripts/logs.sh -f

# View logs with timestamps
./scripts/logs.sh -t
```

## 📚 Development Guidelines

### Code Structure
```
AI4I-Core-microservices/
├── services/                 # Microservices
│   ├── api-gateway-service/
│   ├── auth-service/
│   ├── config-service/
│   ├── metrics-service/
│   ├── telemetry-service/
│   ├── alerting-service/
│   ├── dashboard-service/
│   ├── asr-service/          # NEW
│   ├── tts-service/          # NEW
│   └── nmt-service/          # NEW
├── frontend/                 # NEW
│   └── simple-ui/           # NEW
├── infrastructure/          # Infrastructure setup
│   ├── postgres/           # Database schemas
│   ├── influxdb/           # InfluxDB setup
│   ├── elasticsearch/      # Elasticsearch setup
│   ├── kafka/              # Kafka setup
│   ├── redis/              # Redis configuration
│   └── health-checks/      # Health check scripts
├── tests/                    # NEW
│   ├── integration/         # NEW
│   ├── e2e/                 # NEW
│   ├── fixtures/            # NEW
│   └── conftest.py          # NEW
├── docs/                     # NEW
│   ├── API_DOCUMENTATION.md # NEW
│   ├── DEPLOYMENT.md        # NEW
│   └── TROUBLESHOOTING.md   # NEW
├── scripts/                # Management scripts
├── docker-compose.yml      # Main compose file
├── docker-compose.override.yml  # Development overrides
├── env.template           # Environment template
└── README.md              # This file
```

### Adding New Services

1. Create service directory in `services/`
2. Add Dockerfile, requirements.txt, and main.py
3. Add service to `docker-compose.yml`
4. Create database schema in `infrastructure/postgres/`
5. Add health check script
6. Update management scripts

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

## 🎯 Roadmap

- [x] ASR microservice implementation
- [x] TTS microservice implementation
- [x] NMT microservice implementation
- [x] Simple UI frontend
- [x] WebSocket streaming support
- [x] API documentation with Swagger/OpenAPI
- [x] Integration testing infrastructure
- [ ] Kubernetes deployment manifests
- [ ] Service mesh integration (Istio)
- [ ] Advanced monitoring with Prometheus/Grafana
- [ ] CI/CD pipeline setup
- [ ] Performance optimization
- [ ] Multi-tenant support
