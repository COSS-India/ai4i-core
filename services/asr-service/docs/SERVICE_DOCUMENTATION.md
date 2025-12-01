# ASR Service - Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Prerequisites](#prerequisites)
5. [Installation & Setup](#installation--setup)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Authentication & Authorization](#authentication--authorization)
9. [Usage Examples](#usage-examples)
10. [WebSocket Streaming](#websocket-streaming)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [Development](#development)

---

## Overview

The **ASR (Automatic Speech Recognition) Service** is a microservice that converts speech audio to text using Triton Inference Server. It supports batch processing and real-time streaming.

### Key Capabilities

- **Batch ASR Inference**: Process multiple audio files in a single request
- **Real-time Streaming**: WebSocket-based streaming for low-latency transcription
- **Multi-language Support**: 22+ Indic languages including English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Assamese, Urdu, Sanskrit, Kashmiri, Nepali, Sindhi, Konkani, Dogri, Maithili, Bodo, and Manipuri
- **Multiple Audio Formats**: WAV, MP3, FLAC, OGG, PCM
- **Audio Preprocessing**: Voice Activity Detection (VAD), denoising, normalization
- **Post-processing**: Inverse Text Normalization (ITN), punctuation restoration
- **Multiple Output Formats**: Transcript, SRT, WebVTT

---

## Architecture

### System Architecture

```
Client → API Gateway → ASR Service → Triton Inference Server
                              ↓
                        PostgreSQL (Request Logging)
                              ↓
                        Redis (Rate Limiting, Caching)
```

### Internal Architecture

The service follows a layered architecture pattern:

```
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  (main.py - Entry Point)            │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────────┐
│   Routers   │  │   Middleware     │
│             │  │  - Auth          │
│ - Inference │  │  - Rate Limit    │
│ - Health    │  │  - Logging       │
└──────┬──────┘  │  - Error Handler │
       │         └──────────────────┘
       │
┌──────▼──────┐
│  Services   │
│             │
│ - ASRService│
│ - AudioService│
│ - StreamingService│
└──────┬──────┘
       │
┌──────▼──────┐
│ Repositories│
│             │
│ - ASRRepository│
│ - UserRepository│
│ - APIKeyRepository│
└──────┬──────┘
       │
┌──────▼──────┐
│   Database  │
│  PostgreSQL │
└─────────────┘
```

### Components

1. **Routers** (`routers/`): FastAPI route handlers for API endpoints
2. **Services** (`services/`): Business logic layer
   - `ASRService`: Core ASR inference logic
   - `AudioService`: Audio processing and format conversion
   - `StreamingService`: Real-time WebSocket streaming
3. **Repositories** (`repositories/`): Data access layer
   - `ASRRepository`: ASR request/result persistence
   - `UserRepository`: User data access
   - `APIKeyRepository`: API key validation
4. **Middleware** (`middleware/`): Cross-cutting concerns
   - `AuthProvider`: API key authentication
   - `RateLimitMiddleware`: Request rate limiting
   - `RequestLoggingMiddleware`: Request/response logging
   - `ErrorHandlerMiddleware`: Centralized error handling
5. **Utils** (`utils/`): Utility functions
   - `TritonClient`: Triton Inference Server client
   - `ValidationUtils`: Input validation
   - `ServiceRegistryClient`: Service discovery

---

## Features

### Core Features

1. **Batch ASR Inference**
   - Process multiple audio inputs in a single request
   - Support for base64-encoded audio or file uploads
   - Configurable batch size for optimal performance

2. **Real-time Streaming**
   - Socket.IO WebSocket protocol
   - Low-latency transcription (< 2s response time)
   - Automatic VAD for speech detection
   - Configurable response frequency

3. **Multi-language Support**
   - 22+ Indic languages
   - Automatic language detection (optional)
   - Language-specific model selection

4. **Audio Processing**
   - Format conversion (WAV, MP3, FLAC, OGG, PCM)
   - Sample rate conversion
   - Voice Activity Detection (VAD)
   - Audio normalization and denoising

5. **Post-processing**
   - Inverse Text Normalization (ITN)
   - Punctuation restoration
   - N-best token output
   - Multiple transcription formats (transcript, SRT, WebVTT)

6. **Security & Rate Limiting**
   - API key authentication
   - Per-key rate limiting (minute/hour/day)
   - Request logging and auditing
   - Session management

---

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **PostgreSQL**: 15+ (for request logging and user management)
- **Redis**: 7+ (for rate limiting and caching)
- **Triton Inference Server**: Running with ASR models deployed
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `sqlalchemy>=2.0.0`: ORM
- `asyncpg>=0.29.0`: PostgreSQL async driver
- `redis>=5.0.0`: Redis client
- `tritonclient[http]>=2.40.0`: Triton Inference Server client
- `python-socketio>=5.10.0`: WebSocket support
- `librosa==0.10.1`: Audio processing
- `soundfile>=0.12.1`: Audio I/O

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/asr-service
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp env.template .env
# Edit .env with your configuration
```

### 4. Database Setup

Ensure PostgreSQL is running and the database schema is created. The service uses the `auth_db` database for user management and request logging.

### 5. Redis Setup

Ensure Redis is running and accessible. Redis is used for:
- Rate limiting counters
- API key caching
- Session management

### 6. Triton Server Setup

Ensure Triton Inference Server is running with ASR models deployed. The service connects to Triton for model inference.

### 7. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8087 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8087 --workers 4
```

### 8. Verify Installation

```bash
curl http://localhost:8087/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "asr-service",
  "version": "1.0.0",
  "redis": "healthy",
  "postgres": "healthy",
  "triton": "healthy"
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `asr-service` |
| `SERVICE_PORT` | HTTP port | `8087` |
| `SERVICE_HOST` | Service hostname | `asr-service` |
| `SERVICE_PUBLIC_URL` | Public-facing URL | - |
| `LOG_LEVEL` | Logging level | `INFO` |

#### Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `DB_POOL_SIZE` | Connection pool size | `20` |
| `DB_MAX_OVERFLOW` | Max overflow connections | `10` |

#### Redis Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_PASSWORD` | Redis password | `redis_secure_password_2024` |

#### Triton Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TRITON_ENDPOINT` | Triton server URL | `http://triton-server:8000` |
| `TRITON_API_KEY` | Triton API key | - |
| `TRITON_TIMEOUT` | Request timeout (seconds) | `20` |
| `TRITON_CONCURRENCY` | Max concurrent requests | `20` |

#### ASR Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_SAMPLE_RATE` | Default audio sample rate | `16000` |
| `MAX_AUDIO_DURATION` | Max audio duration (seconds) | `300` |
| `DEFAULT_BATCH_SIZE` | Default batch size | `32` |
| `ENABLE_VAD` | Enable Voice Activity Detection | `true` |
| `ENABLE_POSTPROCESSING` | Enable post-processing | `true` |

#### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_PER_MINUTE` | Requests per minute | `60` |
| `RATE_LIMIT_PER_HOUR` | Requests per hour | `1000` |
| `RATE_LIMIT_PER_DAY` | Requests per day | `10000` |

#### Streaming Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `STREAMING_RESPONSE_FREQUENCY_MS` | Response frequency (ms) | `2000` |
| `STREAMING_MAX_CONNECTIONS` | Max concurrent connections | `100` |
| `STREAMING_BUFFER_SIZE_BYTES` | Buffer size | `32000` |
| `STREAMING_ENABLE_VAD` | Enable VAD in streaming | `true` |
| `STREAMING_TIMEOUT_SECONDS` | Connection timeout | `300` |

---

## API Reference

### Base URL

```
http://localhost:8087
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "service": "asr-service",
  "version": "1.0.0",
  "redis": "healthy",
  "postgres": "healthy",
  "triton": "healthy",
  "timestamp": 1234567890.123
}
```

#### 2. Root Endpoint

**GET** `/`

Get service information.

**Response:**
```json
{
  "name": "ASR Service",
  "version": "1.0.0",
  "status": "running",
  "description": "Automatic Speech Recognition microservice"
}
```

#### 3. Streaming Info

**GET** `/streaming/info`

Get WebSocket streaming endpoint information.

**Response:**
```json
{
  "endpoint": "/socket.io/asr",
  "protocol": "Socket.IO",
  "events": {
    "client_to_server": ["start", "data", "disconnect"],
    "server_to_client": ["ready", "response", "error", "terminate"]
  },
  "connection_params": {
    "serviceId": "ASR model identifier (required)",
    "language": "Language code (required)",
    "samplingRate": "Audio sample rate in Hz (required)",
    "apiKey": "API key for authentication (optional)"
  }
}
```

#### 4. Batch ASR Inference

**POST** `/api/v1/asr/inference`

Perform batch ASR inference on audio inputs.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "config": {
    "serviceId": "vakyansh-asr-en",
    "language": {
      "sourceLanguage": "en"
    },
    "transcriptionFormat": "transcript",
    "numBest": 1,
    "enableITN": true,
    "enablePunctuation": true
  },
  "audio": [
    {
      "audioContent": "base64EncodedAudioData..."
    }
  ]
}
```

**Response:**
```json
{
  "output": [
    {
      "source": "transcribed text here",
      "confidence": 0.95
    }
  ],
  "config": {
    "serviceId": "vakyansh-asr-en",
    "language": {
      "sourceLanguage": "en"
    }
  }
}
```

#### 5. List Models

**GET** `/api/v1/asr/models`

List available ASR models and supported languages.

**Response:**
```json
{
  "models": [
    {
      "model_id": "vakyansh-asr-en",
      "languages": ["en"],
      "description": "English ASR model"
    },
    {
      "model_id": "conformer-asr-multilingual",
      "languages": ["hi", "ta", "te", "kn", "ml"],
      "description": "Multilingual ASR model for Indic languages"
    }
  ],
  "supported_languages": ["en", "hi", "ta", "te", ...],
  "supported_formats": ["wav", "mp3", "flac", "ogg", "pcm"],
  "transcription_formats": ["transcript", "srt", "webvtt"]
}
```

---

## Authentication & Authorization

### API Key Authentication

All inference endpoints require API key authentication. API keys are managed through the Auth Service.

#### Supported Header Formats

1. `Authorization: Bearer <api_key>`
2. `Authorization: ApiKey <api_key>`
3. `Authorization: <api_key>`

#### Example

```bash
curl -X POST http://localhost:8087/api/v1/asr/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"config": {...}, "audio": [...]}'
```

### Rate Limiting

Rate limits are enforced per API key:

- **60 requests per minute**
- **1000 requests per hour**
- **10000 requests per day**

Rate limit headers are included in responses:

- `X-RateLimit-Limit-Minute`: Maximum requests per minute
- `X-RateLimit-Remaining-Minute`: Remaining requests in current minute
- `X-RateLimit-Limit-Hour`: Maximum requests per hour
- `X-RateLimit-Remaining-Hour`: Remaining requests in current hour

When rate limit is exceeded, a `429 Too Many Requests` response is returned with a `Retry-After` header.

### Error Responses

**401 Unauthorized** - Missing or invalid API key:
```json
{
  "detail": {
    "message": "Invalid API key",
    "code": "AUTHENTICATION_ERROR",
    "timestamp": 1234567890.123
  }
}
```

**403 Forbidden** - Insufficient permissions:
```json
{
  "detail": {
    "message": "Not authorized",
    "code": "AUTHORIZATION_ERROR",
    "timestamp": 1234567890.123
  }
}
```

**429 Too Many Requests** - Rate limit exceeded:
```json
{
  "detail": {
    "message": "Rate limit exceeded",
    "code": "RATE_LIMIT_EXCEEDED",
    "timestamp": 1234567890.123
  }
}
```

---

## Usage Examples

### Python Example

```python
import requests
import base64

# Read audio file
with open("audio.wav", "rb") as f:
    audio_data = base64.b64encode(f.read()).decode("utf-8")

# Prepare request
url = "http://localhost:8087/api/v1/asr/inference"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
payload = {
    "config": {
        "serviceId": "vakyansh-asr-en",
        "language": {
            "sourceLanguage": "en"
        },
        "transcriptionFormat": "transcript"
    },
    "audio": [
        {
            "audioContent": audio_data
        }
    ]
}

# Send request
response = requests.post(url, json=payload, headers=headers)
result = response.json()
print(result["output"][0]["source"])
```

### cURL Example

```bash
# Encode audio file
AUDIO_B64=$(base64 -i audio.wav)

# Send request
curl -X POST http://localhost:8087/api/v1/asr/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"config\": {
      \"serviceId\": \"vakyansh-asr-en\",
      \"language\": {
        \"sourceLanguage\": \"en\"
      }
    },
    \"audio\": [
      {
        \"audioContent\": \"$AUDIO_B64\"
      }
    ]
  }"
```

---

## WebSocket Streaming

### Overview

The ASR service supports real-time speech-to-text streaming via Socket.IO WebSocket protocol for low-latency transcription.

### Connection

**Endpoint**: `ws://localhost:8087/socket.io/asr`

**Query Parameters:**
- `serviceId` (required): ASR model identifier
- `language` (required): Language code (e.g., 'en', 'hi', 'ta')
- `samplingRate` (required): Audio sample rate in Hz (e.g., 16000)
- `apiKey` (optional): API key for authentication
- `preProcessors` (optional): JSON array of preprocessors
- `postProcessors` (optional): JSON array of postprocessors

### JavaScript Example

```javascript
const io = require("socket.io-client");

const socket = io("http://localhost:8087/socket.io/asr", {
  transports: ["websocket"],
  query: {
    serviceId: "vakyansh-asr-en",
    language: "en",
    samplingRate: 16000,
    apiKey: "YOUR_API_KEY"
  }
});

// Connection events
socket.on("connect", () => {
  console.log("Connected to ASR service");
  socket.emit("start");
});

socket.on("ready", () => {
  console.log("Ready to receive audio");
  // Start sending audio chunks
  sendAudioChunk();
});

// Send audio data
function sendAudioChunk() {
  // Get audio chunk (e.g., from microphone)
  const audioChunk = getAudioChunk(); // Your audio capture logic
  socket.emit("data", audioChunk);
}

// Receive transcription
socket.on("response", (data) => {
  console.log("Transcription:", data.source);
});

// Error handling
socket.on("error", (error) => {
  console.error("Error:", error);
});

socket.on("disconnect", () => {
  console.log("Disconnected");
});
```

### Events

**Client to Server:**
- `start`: Initialize streaming session
- `data`: Send audio chunk (binary or base64)
- `disconnect`: Close connection

**Server to Client:**
- `ready`: Service ready to receive audio
- `response`: Transcription result
- `error`: Error occurred
- `terminate`: Session terminated

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t asr-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name asr-service \
  -p 8087:8087 \
  --env-file .env \
  asr-service:latest
```

#### Docker Compose

```yaml
services:
  asr-service:
    build: ./services/asr-service
    ports:
      - "8087:8087"
    environment:
      - SERVICE_NAME=asr-service
      - SERVICE_PORT=8087
      - DATABASE_URL=postgresql+asyncpg://...
      - REDIS_HOST=redis
      - TRITON_ENDPOINT=http://triton-server:8000
    depends_on:
      - postgres
      - redis
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: asr-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: asr-service
  template:
    metadata:
      labels:
        app: asr-service
    spec:
      containers:
      - name: asr-service
        image: asr-service:latest
        ports:
        - containerPort: 8087
        env:
        - name: SERVICE_PORT
          value: "8087"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: asr-secrets
              key: database-url
        livenessProbe:
          httpGet:
            path: /health
            port: 8087
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8087
          initialDelaySeconds: 10
          periodSeconds: 5
```

### Production Considerations

1. **Scaling**: Use multiple workers/instances behind a load balancer
2. **Monitoring**: Set up health checks and metrics collection
3. **Logging**: Configure centralized logging (e.g., ELK stack)
4. **Security**: Use HTTPS, secure API keys, and network policies
5. **Performance**: Tune connection pools, batch sizes, and timeouts

---

## Troubleshooting

### Common Issues

#### 1. Service Won't Start

**Problem**: Service fails to start

**Solutions**:
- Check PostgreSQL connection: `psql -h <host> -U <user> -d auth_db`
- Check Redis connection: `redis-cli -h <host> ping`
- Verify environment variables are set correctly
- Check logs: `docker logs asr-service` or check application logs

#### 2. Triton Connection Failed

**Problem**: Cannot connect to Triton Inference Server

**Solutions**:
- Verify `TRITON_ENDPOINT` is correct
- Check Triton server is running: `curl http://<triton-host>:8000/v2/health/ready`
- Verify network connectivity between services
- Check Triton API key if required

#### 3. Authentication Errors

**Problem**: 401 Unauthorized errors

**Solutions**:
- Verify API key is valid and active
- Check API key format in Authorization header
- Ensure API key has required permissions
- Check API key cache TTL setting

#### 4. Rate Limit Exceeded

**Problem**: 429 Too Many Requests

**Solutions**:
- Wait for rate limit window to reset
- Check rate limit headers for reset time
- Consider upgrading API key tier for higher limits
- Implement request queuing/throttling in client

#### 5. Audio Processing Errors

**Problem**: Audio format not supported or processing fails

**Solutions**:
- Verify audio format is supported (WAV, MP3, FLAC, OGG, PCM)
- Check audio sample rate matches model requirements
- Ensure audio is properly base64 encoded
- Check audio file is not corrupted

#### 6. Streaming Connection Issues

**Problem**: WebSocket connection fails or disconnects

**Solutions**:
- Verify Socket.IO client version compatibility
- Check network/firewall allows WebSocket connections
- Verify query parameters are correct
- Check streaming timeout settings

### Debugging

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
uvicorn main:app --host 0.0.0.0 --port 8087
```

Check service health:

```bash
curl http://localhost:8087/health
```

View service logs:

```bash
# Docker
docker logs -f asr-service

# Kubernetes
kubectl logs -f deployment/asr-service
```

---

## Development

### Project Structure

```
asr-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   ├── inference_router.py
│   └── health_router.py
├── services/               # Business logic
│   ├── asr_service.py
│   ├── audio_service.py
│   └── streaming_service.py
├── repositories/           # Data access layer
│   ├── asr_repository.py
│   ├── user_repository.py
│   └── api_key_repository.py
├── models/                 # Pydantic models
│   ├── asr_request.py
│   ├── asr_response.py
│   └── ...
├── middleware/             # Middleware components
│   ├── auth_provider.py
│   ├── rate_limit_middleware.py
│   └── ...
├── utils/                  # Utility functions
│   ├── triton_client.py
│   └── validation_utils.py
├── requirements.txt        # Python dependencies
├── Dockerfile             # Docker image definition
└── env.template           # Environment variable template
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Code Style

Follow PEP 8 and use `black` for formatting:

```bash
black .
```

### Adding New Features

1. Create feature branch: `git checkout -b feature/new-feature`
2. Implement changes following existing patterns
3. Add tests for new functionality
4. Update documentation
5. Submit pull request

---

## Additional Resources

- **API Documentation**: Available at `http://localhost:8087/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8087/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8087/openapi.json`


