# TTS Service - Documentation

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

The **TTS (Text-to-Speech) Service** is a microservice that converts text to natural-sounding speech using Triton Inference Server. It supports batch processing and real-time streaming for 22+ Indic languages with multiple voice options and audio formats.

### Key Capabilities

- **Batch TTS Inference**: Process multiple text inputs in a single request
- **Real-time Streaming**: WebSocket-based streaming for low-latency audio generation
- **Multi-language Support**: 22+ Indic languages with language-specific voices
- **Multiple Voice Options**: Male and female voices for different languages
- **Multiple Audio Formats**: WAV, MP3, FLAC, OGG
- **Configurable Audio Parameters**: Sample rate, format, duration adjustment
- **Voice Management**: Voice catalog and selection

---

## Architecture

### System Architecture

```
Client → API Gateway → TTS Service → Triton Inference Server
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
│ - Voice     │  │  - Error Handler │
└──────┬──────┘  └──────────────────┘
       │
┌──────▼──────┐
│  Services   │
│             │
│ - TTSService│
│ - AudioService│
│ - TextService│
│ - VoiceService│
│ - StreamingService│
└──────┬──────┘
       │
┌──────▼──────┐
│ Repositories│
│             │
│ - TTSRepository│
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

1. **Routers** (`routers/`): FastAPI route handlers
   - `inference_router.py`: TTS inference endpoints
   - `health_router.py`: Health check endpoints
   - `voice_router.py`: Voice management endpoints
2. **Services** (`services/`): Business logic
   - `tts_service.py`: Core TTS inference logic
   - `audio_service.py`: Audio processing and format conversion
   - `text_service.py`: Text processing and normalization
   - `voice_service.py`: Voice catalog and selection
   - `streaming_service.py`: Real-time WebSocket streaming
3. **Repositories** (`repositories/`): Data access layer
   - `tts_repository.py`: Request/result persistence
   - `user_repository.py`: User data access
   - `api_key_repository.py`: API key validation
4. **Middleware** (`middleware/`): Cross-cutting concerns
   - `AuthProvider`: API key authentication
   - `RateLimitMiddleware`: Request rate limiting
   - `RequestLoggingMiddleware`: Request/response logging
   - `ErrorHandlerMiddleware`: Centralized error handling
5. **Utils** (`utils/`): Utility functions
   - `TritonClient`: Triton Inference Server client
   - `ValidationUtils`: Input validation
   - `AudioUtils`: Audio processing utilities
   - `TextUtils`: Text processing utilities
   - `ServiceRegistryClient`: Service discovery

---

## Features

### Core Features

1. **Batch TTS Inference**
   - Process multiple text inputs in a single request
   - Support for base64-encoded audio output
   - Configurable batch size for optimal performance

2. **Real-time Streaming**
   - Socket.IO WebSocket protocol
   - Low-latency audio generation (< 2s response time)
   - Configurable response frequency
   - Text chunking for long inputs

3. **Multi-language Support**
   - 22+ Indic languages
   - Language-specific voice selection
   - Automatic language detection (optional)

4. **Voice Management**
   - Multiple voice options per language
   - Male and female voices
   - Voice catalog API
   - Voice selection by ID

5. **Audio Processing**
   - Format conversion (WAV, MP3, FLAC, OGG)
   - Sample rate conversion
   - Duration adjustment
   - Audio normalization

6. **Text Processing**
   - Text normalization
   - Text chunking for long inputs
   - Input validation
   - Special character handling

7. **Security & Rate Limiting**
   - API key authentication
   - Per-key rate limiting (minute/hour/day)
   - Request logging and auditing
   - Session management

---

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **PostgreSQL**: 15+ (for request logging)
- **Redis**: 7+ (for rate limiting and caching)
- **Triton Inference Server**: Running with TTS models deployed
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `sqlalchemy>=2.0.0`: ORM
- `asyncpg>=0.29.0`: PostgreSQL async driver
- `redis>=5.0.0`: Redis client
- `tritonclient[http]>=2.40.0`: Triton Inference Server client
- `python-socketio>=5.8.0`: WebSocket support
- `librosa>=0.10.0`: Audio processing
- `soundfile>=0.12.1`: Audio I/O
- `pydub>=0.25.1`: Audio manipulation
- `torch>=2.0.0`: PyTorch for audio effects
- `torchaudio>=2.0.0`: Audio processing

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/tts-service
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

Ensure PostgreSQL is running and the database schema is created. The service uses the `auth_db` database for request logging.

### 5. Redis Setup

Ensure Redis is running and accessible. Redis is used for rate limiting and caching.

### 6. Triton Server Setup

Ensure Triton Inference Server is running with TTS models deployed.

### 7. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8088 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8088 --workers 4
```

### 8. Verify Installation

```bash
curl http://localhost:8088/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "tts-service",
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
| `SERVICE_NAME` | Service identifier | `tts-service` |
| `SERVICE_PORT` | HTTP port | `8088` |
| `SERVICE_HOST` | Service hostname | `tts-service` |
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

#### TTS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_SAMPLE_RATE` | Default audio sample rate | `22050` |
| `MAX_TEXT_LENGTH` | Maximum text length | `5000` |
| `DEFAULT_AUDIO_FORMAT` | Default audio format | `wav` |
| `DEFAULT_GENDER` | Default voice gender | `female` |
| `TEXT_CHUNK_SIZE` | Text chunk size for processing | `400` |

#### Audio Generation Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_DURATION_ADJUSTMENT` | Enable duration adjustment | `true` |
| `ENABLE_FORMAT_CONVERSION` | Enable format conversion | `true` |
| `MAX_AUDIO_DURATION` | Maximum audio duration (seconds) | `300` |

#### Streaming Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `STREAMING_RESPONSE_FREQUENCY_MS` | Response frequency (ms) | `2000` |
| `STREAMING_MAX_CONNECTIONS` | Max concurrent connections | `100` |
| `STREAMING_ENABLE_CHUNKING` | Enable text chunking | `true` |
| `STREAMING_TIMEOUT_SECONDS` | Connection timeout | `300` |

#### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_PER_MINUTE` | Requests per minute | `60` |
| `RATE_LIMIT_PER_HOUR` | Requests per hour | `1000` |
| `RATE_LIMIT_PER_DAY` | Requests per day | `10000` |

---

## API Reference

### Base URL

```
http://localhost:8088
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "service": "tts-service",
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
  "service": "tts-service",
  "version": "1.0.0",
  "status": "running",
  "description": "Text-to-Speech microservice"
}
```

#### 3. Streaming Info

**GET** `/streaming/info`

Get WebSocket streaming endpoint information.

**Response:**
```json
{
  "endpoint": "/socket.io/tts",
  "protocol": "Socket.IO",
  "events": {
    "client_to_server": ["start", "data", "disconnect"],
    "server_to_client": ["ready", "response", "error", "terminate"]
  },
  "connection_params": {
    "serviceId": "TTS model identifier (required)",
    "voice_id": "Voice identifier (required)",
    "language": "Language code (required)",
    "gender": "Voice gender (required)",
    "samplingRate": "Audio sample rate in Hz (optional, default: 22050)",
    "audioFormat": "Output audio format (optional, default: wav)",
    "apiKey": "API key for authentication (optional)"
  }
}
```

#### 4. Batch TTS Inference

**POST** `/api/v1/tts/inference`

Perform batch TTS inference on text inputs.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "config": {
    "serviceId": "indic-tts-coqui-dravidian",
    "language": {
      "sourceLanguage": "hi"
    },
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "wav"
  },
  "input": [
    {
      "source": "नमस्ते, आप कैसे हैं?"
    },
    {
      "source": "आज मौसम कैसा है?"
    }
  ]
}
```

**Response:**
```json
{
  "audio": [
    {
      "audioContent": "base64EncodedAudioData..."
    },
    {
      "audioContent": "base64EncodedAudioData..."
    }
  ],
  "config": {
    "serviceId": "indic-tts-coqui-dravidian",
    "language": {
      "sourceLanguage": "hi"
    },
    "gender": "female",
    "samplingRate": 22050,
    "audioFormat": "wav"
  }
}
```

#### 5. List Models

**GET** `/api/v1/tts/models`

List available TTS models and supported languages.

**Response:**
```json
{
  "models": [
    {
      "model_id": "indic-tts-coqui-dravidian",
      "languages": ["ta", "te", "kn", "ml"],
      "description": "Dravidian languages TTS model",
      "supported_genders": ["male", "female"]
    },
    {
      "model_id": "indic-tts-coqui-indo-aryan",
      "languages": ["hi", "bn", "gu", "mr", "pa"],
      "description": "Indo-Aryan languages TTS model",
      "supported_genders": ["male", "female"]
    }
  ],
  "supported_languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai", "brx", "mni"],
  "supported_formats": ["wav", "mp3", "flac", "ogg"],
  "supported_genders": ["male", "female"]
}
```

#### 6. List Voices

**GET** `/api/v1/tts/voices`

List available voices.

**Query Parameters:**
- `language` (optional): Filter by language code
- `gender` (optional): Filter by gender

**Response:**
```json
{
  "voices": [
    {
      "voice_id": "indic-tts-coqui-dravidian-female",
      "language": "ta",
      "gender": "female",
      "name": "Tamil Female Voice",
      "description": "Natural-sounding Tamil female voice"
    },
    {
      "voice_id": "indic-tts-coqui-dravidian-male",
      "language": "ta",
      "gender": "male",
      "name": "Tamil Male Voice",
      "description": "Natural-sounding Tamil male voice"
    }
  ]
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
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"config": {...}, "input": [...]}'
```

### Rate Limiting

Rate limits are enforced per API key:

- **60 requests per minute**
- **1000 requests per hour**
- **10000 requests per day**

When rate limit is exceeded, a `429 Too Many Requests` response is returned.

---

## Usage Examples

### Python Example

```python
import requests
import base64

url = "http://localhost:8088/api/v1/tts/inference"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
payload = {
    "config": {
        "serviceId": "indic-tts-coqui-dravidian",
        "language": {
            "sourceLanguage": "hi"
        },
        "gender": "female",
        "samplingRate": 22050,
        "audioFormat": "wav"
    },
    "input": [
        {
            "source": "नमस्ते, आप कैसे हैं?"
        }
    ]
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()

# Save audio file
audio_data = base64.b64decode(result["audio"][0]["audioContent"])
with open("output.wav", "wb") as f:
    f.write(audio_data)
```

### cURL Example

```bash
curl -X POST http://localhost:8088/api/v1/tts/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "serviceId": "indic-tts-coqui-dravidian",
      "language": {
        "sourceLanguage": "hi"
      },
      "gender": "female",
      "samplingRate": 22050,
      "audioFormat": "wav"
    },
    "input": [
      {
        "source": "नमस्ते, आप कैसे हैं?"
      }
    ]
  }'
```

---

## WebSocket Streaming

### Overview

The TTS service supports real-time text-to-speech streaming via Socket.IO WebSocket protocol for low-latency audio generation.

### Connection

**Endpoint**: `ws://localhost:8088/socket.io/tts`

**Query Parameters:**
- `serviceId` (required): TTS model identifier
- `voice_id` (required): Voice identifier
- `language` (required): Language code
- `gender` (required): Voice gender (male/female)
- `samplingRate` (optional): Audio sample rate in Hz (default: 22050)
- `audioFormat` (optional): Output audio format (default: wav)
- `apiKey` (optional): API key for authentication

### JavaScript Example

```javascript
const io = require("socket.io-client");

const socket = io("http://localhost:8088/socket.io/tts", {
  transports: ["websocket"],
  query: {
    serviceId: "indic-tts-coqui-dravidian",
    voice_id: "indic-tts-coqui-dravidian-female",
    language: "ta",
    gender: "female",
    samplingRate: 22050,
    apiKey: "YOUR_API_KEY"
  }
});

// Connection events
socket.on("connect", () => {
  console.log("Connected to TTS service");
  socket.emit("start");
});

socket.on("ready", () => {
  console.log("Ready to receive text");
  // Send text for synthesis
  socket.emit("data", "नमस्ते, आप कैसे हैं?");
});

// Receive audio
socket.on("response", (data) => {
  console.log("Audio received:", data.audioContent);
  // Play audio or save to file
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
- `data`: Send text for synthesis
- `disconnect`: Close connection

**Server to Client:**
- `ready`: Service ready to receive text
- `response`: Audio generation result
- `error`: Error occurred
- `terminate`: Session terminated

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t tts-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name tts-service \
  -p 8088:8088 \
  --env-file .env \
  tts-service:latest
```

### Production Considerations

1. **Scaling**: Use multiple workers/instances behind a load balancer
2. **Monitoring**: Set up health checks and metrics collection
3. **Logging**: Configure centralized logging
4. **Security**: Use HTTPS, secure API keys, and network policies
5. **Performance**: Tune connection pools, batch sizes, and timeouts

---

## Troubleshooting

### Common Issues

#### 1. Service Won't Start

**Problem**: Service fails to start

**Solutions**:
- Check PostgreSQL connection
- Check Redis connection
- Verify environment variables are set correctly
- Check logs for detailed error messages

#### 2. Triton Connection Failed

**Problem**: Cannot connect to Triton Inference Server

**Solutions**:
- Verify `TRITON_ENDPOINT` is correct
- Check Triton server is running
- Verify network connectivity
- Check Triton API key if required

#### 3. Audio Generation Fails

**Problem**: Audio generation fails or produces errors

**Solutions**:
- Verify text is in correct language
- Check voice_id matches language and gender
- Ensure text length is within limits
- Check audio format and sample rate settings

#### 4. Streaming Connection Issues

**Problem**: WebSocket connection fails or disconnects

**Solutions**:
- Verify Socket.IO client version compatibility
- Check network/firewall allows WebSocket connections
- Verify query parameters are correct
- Check streaming timeout settings

---

## Development

### Project Structure

```
tts-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   ├── inference_router.py
│   ├── health_router.py
│   └── voice_router.py
├── services/               # Business logic
│   ├── tts_service.py
│   ├── audio_service.py
│   ├── text_service.py
│   ├── voice_service.py
│   └── streaming_service.py
├── repositories/           # Data access layer
│   ├── tts_repository.py
│   ├── user_repository.py
│   └── api_key_repository.py
├── models/                 # Pydantic models
│   ├── tts_request.py
│   ├── tts_response.py
│   └── ...
├── middleware/             # Middleware components
│   ├── auth_provider.py
│   ├── rate_limit_middleware.py
│   └── ...
├── utils/                  # Utility functions
│   ├── triton_client.py
│   ├── validation_utils.py
│   └── ...
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

---

## Additional Resources

- **API Documentation**: Available at `http://localhost:8088/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8088/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8088/openapi.json`


