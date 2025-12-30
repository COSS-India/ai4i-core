# LLM Service - Documentation

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

The **LLM (Large Language Model) Service** is a microservice that provides text processing capabilities using large language models via Triton Inference Server. It supports text generation, translation, summarization, and other language processing tasks for multiple Indic languages.

### Key Capabilities

- **Text Processing**: Language model inference for various NLP tasks
- **Multi-language Support**: 13+ Indic languages including English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Assamese, and Urdu
- **Batch Processing**: Process multiple text inputs in a single request
- **Request Logging**: Track all inference requests for analytics
- **Rate Limiting**: Per-API-key rate limiting
- **Authentication**: API key-based authentication

---

## Architecture

### System Architecture

```
Client → API Gateway → LLM Service → Triton Inference Server
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
│ - LLMService│
└──────┬──────┘
       │
┌──────▼──────┐
│ Repositories│
│             │
│ - LLMRepository│
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
   - `inference_router.py`: LLM inference endpoints
   - `health_router.py`: Health check endpoints
2. **Services** (`services/`): Business logic
   - `llm_service.py`: Core LLM inference logic
3. **Repositories** (`repositories/`): Data access layer
   - `llm_repository.py`: Request/result persistence
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

---

## Features

### Core Features

1. **LLM Inference**
   - Text generation
   - Text translation
   - Text summarization
   - Other language processing tasks
   - Batch processing support

2. **Multi-language Support**
   - 13+ Indic languages
   - Language-specific model selection
   - Input/output language configuration

3. **Request Management**
   - Request logging to database
   - Result persistence
   - Request tracking and analytics
   - Error handling and retry logic

4. **Security & Rate Limiting**
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
- **Triton Inference Server**: Running with LLM models deployed
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
cd aiv4-core/services/llm-service
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

Ensure Triton Inference Server is running with LLM models deployed.

### 7. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8090 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8090 --workers 4
```

### 8. Verify Installation

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "llm-service",
  "version": "1.0.0"
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `llm-service` |
| `SERVICE_PORT` | HTTP port | `8090` |
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
| `TRITON_ENDPOINT` | Triton server URL | `http://13.220.11.146:8000` |
| `TRITON_API_KEY` | Triton API key | - |
| `TRITON_TIMEOUT` | Request timeout (seconds) | `300` |
| `TRITON_CONCURRENCY` | Max concurrent requests | `20` |

#### LLM Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_BATCH_SIZE` | Maximum batch size | `100` |
| `MAX_TEXT_LENGTH` | Maximum text length | `50000` |
| `DEFAULT_INPUT_LANGUAGE` | Default input language | `en` |
| `DEFAULT_OUTPUT_LANGUAGE` | Default output language | `en` |

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
http://localhost:8090
```

### Endpoints

#### 1. Health Check

**GET** `/health`

Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy",
  "service": "llm-service",
  "version": "1.0.0"
}
```

#### 2. Root Endpoint

**GET** `/`

Get service information.

**Response:**
```json
{
  "service": "llm-service",
  "version": "1.0.0",
  "status": "running",
  "description": "Large Language Model microservice"
}
```

#### 3. LLM Inference

**POST** `/api/v1/llm/inference`

Perform LLM inference on text inputs.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "config": {
    "serviceId": "llm",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "modelParameters": {
      "temperature": 0.7,
      "maxTokens": 512
    }
  },
  "input": [
    {
      "source": "Hello, how are you?"
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
    }
  ],
  "config": {
    "serviceId": "llm",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    }
  }
}
```

#### 4. List Models

**GET** `/api/v1/llm/models`

List available LLM models.

**Response:**
```json
{
  "models": [
    {
      "model_id": "llm",
      "provider": "AI4Bharat",
      "description": "LLM model for text processing, translation, and generation",
      "max_batch_size": 100,
      "supported_languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa", "or", "as", "ur"]
    }
  ],
  "total_models": 1
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
curl -X POST http://localhost:8090/api/v1/llm/inference \
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

url = "http://localhost:8090/api/v1/llm/inference"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}
payload = {
    "config": {
        "serviceId": "llm",
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
    print(f"Input: {output['source']}")
    print(f"Output: {output['target']}")
```

### cURL Example

```bash
curl -X POST http://localhost:8090/api/v1/llm/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "serviceId": "llm",
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

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t llm-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name llm-service \
  -p 8090:8090 \
  --env-file .env \
  llm-service:latest
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

#### 3. Authentication Errors

**Problem**: 401 Unauthorized errors

**Solutions**:
- Verify API key is valid and active
- Check API key format in Authorization header
- Ensure API key has required permissions

#### 4. Rate Limit Exceeded

**Problem**: 429 Too Many Requests

**Solutions**:
- Wait for rate limit window to reset
- Check rate limit headers for reset time
- Consider upgrading API key tier for higher limits

---

## Development

### Project Structure

```
llm-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   ├── inference_router.py
│   └── health_router.py
├── services/               # Business logic
│   └── llm_service.py
├── repositories/           # Data access layer
│   ├── llm_repository.py
│   ├── user_repository.py
│   └── api_key_repository.py
├── models/                 # Pydantic models
│   ├── llm_request.py
│   ├── llm_response.py
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

---

## Additional Resources

- **API Documentation**: Available at `http://localhost:8090/docs` (Swagger UI)
- **ReDoc**: Available at `http://localhost:8090/redoc`
- **OpenAPI Spec**: Available at `http://localhost:8090/openapi.json`


