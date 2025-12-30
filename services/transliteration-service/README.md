# Transliteration Service

Transliteration microservice for converting text from one script to another. Part of the AI4ICore platform.

## Features

- **Multi-Language Support**: 24+ Indic languages including Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, and more
- **Word-Level & Sentence-Level**: Supports both word-level and sentence-level transliteration
- **Top-K Suggestions**: Get multiple transliteration suggestions for word-level transliteration
- **Batch Processing**: Process up to 100 texts per request
- **Triton Integration**: Uses NVIDIA Triton Inference Server for fast inference
- **AI4ICore Observability**: Automatic metrics extraction and monitoring
- **Authentication & Authorization**: API key-based authentication with Redis caching
- **Rate Limiting**: Configurable rate limiting per minute/hour/day
- **Health Checks**: Kubernetes-ready health, readiness, and liveness probes

## Architecture

The transliteration service follows a clean, modular architecture:

```
transliteration-service/
├── main.py                      # FastAPI application entry point
├── models/                      # Pydantic models and database schemas
│   ├── transliteration_request.py
│   ├── transliteration_response.py
│   ├── database_models.py
│   └── auth_models.py
├── repositories/                # Database access layer
│   ├── transliteration_repository.py
│   ├── api_key_repository.py
│   ├── user_repository.py
│   └── session_repository.py
├── services/                    # Business logic layer
│   ├── transliteration_service.py
│   └── text_service.py
├── routers/                     # API endpoints
│   ├── inference_router.py
│   └── health_router.py
├── middleware/                  # Authentication, rate limiting, logging
│   ├── auth_provider.py
│   ├── rate_limit_middleware.py
│   ├── request_logging.py
│   └── error_handler_middleware.py
└── utils/                       # Utility functions
    ├── triton_client.py
    ├── validation_utils.py
    └── service_registry_client.py
```

## API Endpoints

### Transliteration Inference

**POST** `/api/v1/transliteration/inference`

Transliterate text from source language to target language.

**Request Body:**
```json
{
  "input": [
    {"source": "namaste"}
  ],
  "config": {
    "serviceId": "ai4bharat/indicxlit",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "isSentence": false,
    "numSuggestions": 3
  }
}
```

**Response:**
```json
{
  "output": [
    {
      "source": "namaste",
      "target": ["नमस्ते", "नमस्ते", "नमस्ते"]
    }
  ]
}
```

### Model & Service Information

- **GET** `/api/v1/transliteration/models` - List available transliteration models
- **GET** `/api/v1/transliteration/services` - List available transliteration services
- **GET** `/api/v1/transliteration/languages` - Get supported languages

### Health Checks

- **GET** `/health` - Overall service health
- **GET** `/api/v1/health` - Detailed health check with dependencies
- **GET** `/api/v1/ready` - Readiness check for Kubernetes
- **GET** `/api/v1/live` - Liveness check for Kubernetes

## Configuration

### Environment Variables

Copy `env.template` to `.env` and configure:

```bash
# Service Configuration
SERVICE_NAME=transliteration-service
SERVICE_PORT=8090
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/auth_db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# Triton
TRITON_ENDPOINT=13.200.133.97:8000
TRITON_API_KEY=your_triton_api_key

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

## Running the Service

### Using Docker

```bash
# Build the image
docker build -t transliteration-service:latest -f services/transliteration-service/Dockerfile .

# Run the container
docker run -d \
  --name transliteration-service \
  -p 8090:8090 \
  --env-file services/transliteration-service/.env \
  transliteration-service:latest
```

### Using Docker Compose

```bash
# Start the service with dependencies
docker-compose up transliteration-service

# Scale the service
docker-compose up --scale transliteration-service=3
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -e ../../libs/ai4icore_observability

# Run the service
cd services/transliteration-service
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

## Supported Languages

The transliteration service supports 24+ Indic languages:

- English (en), Hindi (hi), Tamil (ta), Telugu (te), Kannada (kn)
- Malayalam (ml), Bengali (bn), Gujarati (gu), Marathi (mr), Punjabi (pa)
- Odia (or), Assamese (as), Urdu (ur), Sanskrit (sa), Kashmiri (ks)
- Nepali (ne), Sindhi (sd), Konkani (kok), Dogri (doi), Maithili (mai)
- Bodo (brx), Manipuri (mni), Santali (sat), Goan Konkani (gom)

## Transliteration Modes

### Sentence-Level Transliteration

Transliterate complete sentences while preserving context and meaning.

```json
{
  "config": {
    "isSentence": true,
    "numSuggestions": 0
  }
}
```

### Word-Level Transliteration

Transliterate individual words with optional top-k suggestions.

```json
{
  "config": {
    "isSentence": false,
    "numSuggestions": 3
  }
}
```

## Observability

The service integrates with AI4ICore Observability Plugin for automatic metrics extraction:

- **Request Metrics**: Character counts, processing times, success/error rates
- **Language Metrics**: Per-language pair statistics
- **Service Metrics**: API key usage, user activity
- **System Metrics**: CPU, memory, request latency

Metrics are automatically exported to:
- Prometheus (metrics)
- Elasticsearch (logs)
- InfluxDB (time-series data)

## Authentication

API key-based authentication with Redis caching for performance.

**Header Format:**
```
Authorization: Bearer your_api_key_here
```

or

```
Authorization: ApiKey your_api_key_here
```

## Error Handling

The service provides detailed error responses:

```json
{
  "detail": {
    "message": "Error message",
    "type": "ErrorType",
    "timestamp": 1234567890.123
  },
  "status_code": 400
}
```

Common error codes:
- `400` - Bad Request (validation errors)
- `401` - Unauthorized (missing/invalid API key)
- `403` - Forbidden (insufficient permissions)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error
- `503` - Service Unavailable (dependencies down)

## Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=. --cov-report=html tests/

# Test transliteration endpoint
curl -X POST http://localhost:8090/api/v1/transliteration/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_key" \
  -d '{
    "input": [{"source": "namaste"}],
    "config": {
      "serviceId": "ai4bharat/indicxlit",
      "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
      "isSentence": false,
      "numSuggestions": 3
    }
  }'
```

## License

MIT License

## Support

For issues and questions:
- GitHub Issues: https://github.com/AI4X/ai4icore/issues
- Email: support@ai4x.com

## Contributors

- AI4ICore Team

