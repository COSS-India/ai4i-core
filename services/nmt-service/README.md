# NMT Service (Neural Machine Translation)

Microservice for translating text between languages using Triton Inference Server.

## Features

- **Batch NMT inference** (max 90 texts per request)
- **Support for 22+ Indic languages** including Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Oriya, Assamese, Urdu, and more
- **Bidirectional translation** (any language pair)
- **Script code support** (e.g., Devanagari, Arabic, Tamil)
- **Text preprocessing and normalization**
- **High-throughput batch processing**
- **Async/await architecture** for optimal performance
- **Database logging** for request tracking and analytics

## Architecture

```
Client → API Gateway → NMT Service → Triton Server
                    ↓
                PostgreSQL
                    ↓
                  Redis
```

The service follows a layered architecture:

- **Routers**: FastAPI endpoints for HTTP requests
- **Services**: Business logic for NMT processing
- **Repositories**: Database operations
- **Utils**: Utility functions for text processing and Triton integration

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Triton Inference Server with NMT models
- Docker (optional)

## Installation

1. **Clone repository**

   ```bash
   git clone <repository-url>
   cd Ai4V-C/services/nmt-service
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**

   ```bash
   cp env.template .env
   # Edit .env with your configuration
   ```

4. **Run migrations** (if needed)
   ```bash
   alembic upgrade head
   ```

## Configuration

### Environment Variables

| Variable          | Description                  | Default                   |
| ----------------- | ---------------------------- | ------------------------- |
| `SERVICE_PORT`    | Service port                 | 8089                      |
| `DATABASE_URL`    | PostgreSQL connection string | postgresql+asyncpg://...  |
| `REDIS_HOST`      | Redis host                   | redis                     |
| `REDIS_PORT`      | Redis port                   | 6379                      |
| `TRITON_ENDPOINT` | Triton server URL            | http://triton-server:8000 |
| `MAX_BATCH_SIZE`  | Maximum texts per batch      | 90                        |
| `MAX_TEXT_LENGTH` | Maximum text length          | 10000                     |

### Database Setup

The service uses two main tables:

- `nmt_requests`: Stores request metadata and status
- `nmt_results`: Stores individual translation results

## Usage

### Start Service

```bash
uvicorn main:app --host 0.0.0.0 --port 8089
```

### API Endpoints

#### 1. Batch Translation

**POST** `/api/v1/nmt/inference`

Translate multiple texts in a single request.

**Request Body:**

```json
{
  "input": [{ "source": "Hello world" }, { "source": "Good morning" }],
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi",
      "sourceScriptCode": "Latn",
      "targetScriptCode": "Deva"
    }
  }
}
```

**Response:**

```json
{
  "output": [
    {
      "source": "Hello world",
      "target": "नमस्ते दुनिया"
    },
    {
      "source": "Good morning",
      "target": "शुभ प्रभात"
    }
  ]
}
```

#### 2. List Models

**GET** `/api/v1/nmt/models`

Get available NMT models and language pairs.

#### 3. Health Checks

- **GET** `/api/v1/nmt/health` - Overall service health
- **GET** `/api/v1/nmt/ready` - Readiness check
- **GET** `/api/v1/nmt/live` - Liveness check

## Authentication & Authorization

### API Key Authentication

All NMT inference endpoints require API key authentication. Include your API key in the request header:

```bash
curl -X POST http://localhost:8089/api/v1/nmt/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

**Supported Header Formats:**

- `Authorization: Bearer <api_key>`
- `Authorization: ApiKey <api_key>`
- `Authorization: <api_key>`

### Rate Limiting

API requests are rate-limited per API key:

- **60 requests per minute**
- **1000 requests per hour**
- **10000 requests per day**

When rate limit is exceeded, you'll receive a `429 Too Many Requests` response with a `Retry-After` header.

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

### Request Logging

All authenticated requests are logged to the database with:

- User ID
- API key ID
- Session ID (if applicable)
- Request metadata (model, source/target languages, text length)
- Processing time
- Status (processing, completed, failed)

Logs are stored in `nmt_requests` and `nmt_results` tables for auditing and analytics.

## Language Detection

### Automatic Language Detection

The NMT service can automatically detect the source language if not specified:

```json
{
  "input": [{ "source": "नमस्ते दुनिया" }],
  "config": {
    "serviceId": "indictrans-v2-all",
    "language": {
      "sourceLanguage": "auto",
      "targetLanguage": "en"
    }
  }
}
```

**Supported Detection Methods:**

- Unicode script detection (Devanagari → Hindi, Arabic → Urdu, etc.)
- Confidence scoring (0.0-1.0)
- Fallback to English if detection fails

**Detection Confidence Threshold**: 0.7 (configurable via `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD`)

### Confidence Scoring

Each translation includes a confidence score indicating translation quality:

```json
{
  "output": [
    {
      "source": "Hello world",
      "target": "नमस्ते दुनिया",
      "confidence": 0.95,
      "language_detected": "en"
    }
  ]
}
```

**Confidence Score Interpretation:**

- 0.9-1.0: High confidence (excellent translation)
- 0.7-0.9: Medium confidence (good translation)
- 0.5-0.7: Low confidence (acceptable translation)
- <0.5: Very low confidence (may need review)

### Example Usage with curl

```bash
# Translate text from English to Hindi (with authentication)
curl -X POST "http://localhost:8089/api/v1/nmt/inference" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"source": "Hello world"}],
    "config": {
      "serviceId": "indictrans-v2-all",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      }
    }
  }'

# Check service health
curl "http://localhost:8089/api/v1/nmt/health"
```

## Language Support

### Supported Languages

- **English** (en)
- **Hindi** (hi) - Devanagari script
- **Tamil** (ta) - Tamil script
- **Telugu** (te) - Telugu script
- **Kannada** (kn) - Kannada script
- **Malayalam** (ml) - Malayalam script
- **Bengali** (bn) - Bengali script
- **Gujarati** (gu) - Gujarati script
- **Marathi** (mr) - Devanagari script
- **Punjabi** (pa) - Gurmukhi script
- **Oriya** (or) - Oriya script
- **Assamese** (as) - Bengali script
- **Urdu** (ur) - Arabic script
- And more...

### Script Code Support

The service supports script codes for languages with multiple writing systems:

- `hi_Deva` - Hindi in Devanagari script
- `ur_Arab` - Urdu in Arabic script
- `ta_Taml` - Tamil in Tamil script
- `te_Telu` - Telugu in Telugu script

## Docker Deployment

### Build Image

```bash
docker build -t nmt-service:latest .
```

### Run Container

```bash
docker run -p 8089:8089 \
  --env-file .env \
  --network ai4v-network \
  nmt-service:latest
```

### Docker Compose

```yaml
version: "3.8"
services:
  nmt-service:
    build: .
    ports:
      - "8089:8089"
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/db
      - REDIS_HOST=redis
      - TRITON_ENDPOINT=http://triton-server:8000
    depends_on:
      - postgres
      - redis
      - triton-server
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black .
flake8 .
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Troubleshooting

### Common Issues

1. **Triton server not ready**

   - Check if Triton server is running
   - Verify NMT models are loaded
   - Check network connectivity

2. **Database connection failed**

   - Verify PostgreSQL is running
   - Check connection string
   - Ensure database exists

3. **Redis connection failed**
   - Check Redis server status
   - Verify credentials
   - Check network connectivity

### Logging

The service uses structured logging. Set `LOG_LEVEL` environment variable to control verbosity:

- `DEBUG` - Detailed debug information
- `INFO` - General information (default)
- `WARNING` - Warning messages
- `ERROR` - Error messages only

### Performance Tuning

1. **Batch Size**: Adjust `MAX_BATCH_SIZE` based on your Triton server capacity
2. **Database Pool**: Tune `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`
3. **Redis**: Configure Redis memory and persistence settings
4. **Triton**: Optimize Triton server configuration for your hardware

## License

This project is licensed under the MIT License.

## Credits

- **AI4Bharat** for the IndicTrans2 model
- **Dhruva Platform** for the original implementation
- **Triton Inference Server** for model serving
- **FastAPI** for the web framework
