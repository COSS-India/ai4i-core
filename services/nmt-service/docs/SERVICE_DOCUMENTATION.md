# NMT Service - Documentation

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
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)
12. [Development](#development)

---

## Overview

The **NMT (Neural Machine Translation) Service** is a microservice that provides neural machine translation capabilities for 22+ Indic languages using Triton Inference Server. It supports bidirectional translation with automatic language detection and script code handling.

### Key Capabilities

- **Neural Machine Translation**: High-quality translation between 22+ Indic languages
- **Bidirectional Translation**: Translate from any supported language to any other
- **Batch Processing**: Process up to 90 text inputs in a single request
- **Automatic Language Detection**: Optional automatic source language detection
- **Text Normalization**: Automatic text normalization and script code handling
- **Request Logging**: Track all translation requests for analytics
- **Rate Limiting**: Per-API-key rate limiting

---

## Architecture

### System Architecture

```
Client → API Gateway → NMT Service → Triton Inference Server
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
│ - NMTService│
│ - TextService│
│ - LanguageDetectionService│
└──────┬──────┘
       │
┌──────▼──────┐
│ Repositories│
│             │
│ - NMTRepository│
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
   - `inference_router.py`: NMT inference endpoints
   - `health_router.py`: Health check endpoints
2. **Services** (`services/`): Business logic
   - `nmt_service.py`: Core NMT inference logic
   - `text_service.py`: Text processing and normalization
   - `language_detection_service.py`: Automatic language detection
3. **Repositories** (`repositories/`): Data access layer
   - `nmt_repository.py`: Request/result persistence
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
   - `TextUtils`: Text processing utilities
   - `ServiceRegistryClient`: Service discovery

---

## Features

### Core Features

1. **Neural Machine Translation**
   - High-quality translation between 22+ Indic languages
   - Support for bidirectional translation pairs
   - Batch processing (up to 90 texts per request)
   - Configurable model parameters

2. **Language Support**
   - 22+ Indic languages: English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Assamese, Urdu, Sanskrit, Kashmiri, Nepali, Sindhi, Konkani, Dogri, Maithili, Bodo, Manipuri
   - Automatic language detection (optional)
   - Script code handling

3. **Text Processing**
   - Text normalization
   - Script detection
   - Input validation
   - Output formatting

4. **Request Management**
   - Request logging to database
   - Result persistence
   - Request tracking and analytics
   - Error handling and retry logic

5. **Security & Rate Limiting**
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
- **Triton Inference Server**: Running with NMT models deployed
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `sqlalchemy>=2.0.0`: ORM
- `asyncpg>=0.29.0`: PostgreSQL async driver
- `redis>=5.0.0`: Redis client
- `tritonclient[http]>=2.40.0`: Triton Inference Server client
- `httpx>=0.25.0`: HTTP client
- `numpy>=1.24.0`: Array operations
- `pydantic>=2.4.0`: Data validation

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/nmt-service
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

Ensure Triton Inference Server is running with NMT models deployed.

### 7. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8089 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8089 --workers 4
```

### 8. Verify Installation

```bash
curl http://localhost:8089/health
```

Expected response:
```json
{
  "service": "nmt-service",
  "status": "ok",
  "redis_ok": true,
  "db_ok": true,
  "version": "1.0.2"
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `nmt-service` |
| `SERVICE_PORT` | HTTP port | `8089` |
| `SERVICE_HOST` | Service hostname | `nmt-service` |
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
| `REDIS_TIMEOUT` | Redis connection timeout | `10` |

#### Triton Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TRITON_ENDPOINT` | Triton server URL | `http://triton-server:8000` |
| `TRITON_API_KEY` | Triton API key | - |
| `TRITON_TIMEOUT` | Request timeout (seconds) | `20` |
| `TRITON_CONCURRENCY` | Max concurrent requests | `20` |

#### NMT Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_BATCH_SIZE` | Maximum batch size | `90` |
| `MAX_TEXT_LENGTH` | Maximum text length | `10000` |
| `DEFAULT_SOURCE_LANGUAGE` | Default source language | `en` |
| `DEFAULT_TARGET_LANGUAGE` | Default target language | `hi` |
| `ENABLE_TEXT_NORMALIZATION` | Enable text normalization | `true` |
| `ENABLE_SCRIPT_DETECTION` | Enable script detection | `true` |

#### Language Detection

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_AUTO_LANGUAGE_DETECTION` | Enable auto language detection | `true` |
| `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD` | Confidence threshold | `0.7` |

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
http://localhost:8089
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "service": "nmt-service",
  "status": "ok",
  "redis_ok": true,
  "db_ok": true,
  "version": "1.0.2"
}
```

#### 2. Root Endpoint

**GET** `/`

Get service information.

**Response:**
```json
{
  "service": "nmt-service",
  "version": "1.0.2",
  "status": "running",
  "description": "Neural Machine Translation microservice",
  "redis_available": true,
  "redis_host": "redis"
}
```

#### 3. NMT Inference

**POST** `/api/v1/nmt/inference`

Perform batch NMT inference on text inputs.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "modelParameters": {
      "beamSize": 5,
      "lengthPenalty": 0.6
    }
  },
  "input": [
    {
      "source": "Hello, how are you?"
    },
    {
      "source": "What is the weather today?"
    }
  ]
}
```

**Response:**
```json
{
  "output": [
    {
      "source": "Hello, how are you?",
      "target": "नमस्ते, आप कैसे हैं?"
    },
    {
      "source": "What is the weather today?",
      "target": "आज मौसम कैसा है?"
    }
  ],
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    }
  }
}
```

#### 4. List Models

**GET** `/api/v1/nmt/models`

List available NMT models and supported language pairs.

**Response:**
```json
{
  "models": [
    {
      "model_id": "indictrans-v2-all",
      "description": "Neural Machine Translation model for 22+ Indic languages",
      "supported_language_pairs": [
        {"source": "en", "target": "hi"},
        {"source": "hi", "target": "en"},
        {"source": "en", "target": "ta"},
        {"source": "ta", "target": "en"}
      ],
      "max_batch_size": 90
    }
  ],
  "supported_languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai", "brx", "mni"]
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
curl -X POST http://localhost:8089/api/v1/nmt/inference \
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

url = "http://localhost:8089/api/v1/nmt/inference"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
payload = {
    "config": {
        "serviceId": "indictrans-v2-all",
        "language": {
            "sourceLanguage": "en",
            "targetLanguage": "hi"
        }
    },
    "input": [
        {
            "source": "Hello, how are you?"
        },
        {
            "source": "What is the weather today?"
        }
    ]
}

response = requests.post(url, json=payload, headers=headers)
result = response.json()

for output in result["output"]:
    print(f"English: {output['source']}")
    print(f"Hindi: {output['target']}")
    print()
```

### cURL Example

```bash
curl -X POST http://localhost:8089/api/v1/nmt/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "serviceId": "indictrans-v2-all",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      }
    },
    "input": [
      {
        "source": "Hello, how are you?"
      }
    ]
  }'
```

### Batch Translation Example

```python
# Translate multiple texts in a single request
texts = [
    "Good morning",
    "How are you?",
    "Thank you very much",
    "Have a nice day"
]

payload = {
    "config": {
        "serviceId": "indictrans-v2-all",
        "language": {
            "sourceLanguage": "en",
            "targetLanguage": "hi"
        }
    },
    "input": [{"source": text} for text in texts]
}

response = requests.post(url, json=payload, headers=headers)
results = response.json()["output"]

for result in results:
    print(f"{result['source']} → {result['target']}")
```

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t nmt-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name nmt-service \
  -p 8089:8089 \
  --env-file .env \
  nmt-service:latest
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
- Check Redis connection (service will start but with reduced functionality)
- Verify environment variables are set correctly
- Check logs for detailed error messages

#### 2. Triton Connection Failed

**Problem**: Cannot connect to Triton Inference Server

**Solutions**:
- Verify `TRITON_ENDPOINT` is correct
- Check Triton server is running
- Verify network connectivity
- Check Triton API key if required

#### 3. Language Pair Not Supported

**Problem**: Translation fails for unsupported language pair

**Solutions**:
- Check supported language pairs using `/api/v1/nmt/models`
- Verify source and target languages are correct
- Ensure model supports the language pair

#### 4. Batch Size Exceeded

**Problem**: Request fails with batch size error

**Solutions**:
- Reduce number of texts in request (max 90)
- Split large batches into smaller requests
- Check `MAX_BATCH_SIZE` configuration

---

## Development

### Project Structure

```
nmt-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   ├── inference_router.py
│   └── health_router.py
├── services/               # Business logic
│   ├── nmt_service.py
│   ├── text_service.py
│   └── language_detection_service.py
├── repositories/           # Data access layer
│   ├── nmt_repository.py
│   ├── user_repository.py
│   └── api_key_repository.py
├── models/                 # Pydantic models
│   ├── nmt_request.py
│   ├── nmt_response.py
│   └── ...
├── middleware/             # Middleware components
│   ├── auth_provider.py
│   ├── rate_limit_middleware.py
│   └── ...
├── utils/                  # Utility functions
│   ├── triton_client.py
│   ├── validation_utils.py
│   └── service_registry_client.py
├── tests/                  # Test files
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

- **API Documentation**: Available at `http://localhost:8089/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8089/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8089/openapi.json`


