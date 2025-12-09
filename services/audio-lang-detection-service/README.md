# Audio Language Detection Service

Audio Language Detection microservice for detecting the language of audio content and returning language code, confidence scores, and all detection scores.

## Overview

This service provides audio language detection inference capabilities using Triton Inference Server. It processes audio files and identifies the language with confidence scores.

## Features

- **Audio Language Detection**: Detects the language of audio files
- **Batch Processing**: Supports processing multiple audio files in a single request
- **Confidence Scores**: Returns confidence scores and top scores for language detection
- **Triton Integration**: Uses Triton Inference Server for model inference
- **Observability**: Integrated with AI4ICore Observability Plugin for metrics and monitoring
- **Rate Limiting**: Redis-based rate limiting per API key
- **Service Registry**: Automatic registration with the service registry

## API Endpoints

### POST `/api/v1/audio-lang-detection/inference`

Perform audio language detection inference on one or more audio files.

**Request Body:**
```json
{
  "controlConfig": {
    "dataTracking": true
  },
  "config": {
    "serviceId": "ai4bharat/audio-lang-detection"
  },
  "audio": [
    {
      "audioContent": "base64_encoded_audio",
      "audioUri": "https://example.com/audio.wav"
    }
  ]
}
```

**Response:**
```json
{
  "taskType": "audio-lang-detection",
  "output": [
    {
      "language_code": "ta: Tamil",
      "confidence": 0.999923586845398,
      "all_scores": {
        "predicted_language": "ta: Tamil",
        "confidence": 0.999923586845398,
        "top_scores": [
          0.999923586845398,
          0.00006958437006687745,
          0.0000047704766075185034,
          0.0000021015366655774415,
          3.07008640731965e-8
        ]
      }
    }
  ],
  "config": {
    "serviceId": "ai4bharat/audio-lang-detection"
  }
}
```

### GET `/health`

Health check endpoint that verifies Redis, PostgreSQL, and Triton connectivity.

## Configuration

See `env.template` for all available environment variables.

### Key Configuration Variables

- `TRITON_ENDPOINT`: Triton Inference Server endpoint (default: `65.1.35.3:8100`)
- `SERVICE_PORT`: Service port (default: `8096`)
- `REDIS_HOST`: Redis host for rate limiting
- `DATABASE_URL`: PostgreSQL connection string

## Running the Service

### Using Docker Compose

The service is included in `docker-compose.yml`:

```bash
docker compose up audio-lang-detection-service
```

### Standalone

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ../../libs/ai4icore_observability

# Set environment variables
export TRITON_ENDPOINT=65.1.35.3:8100
export SERVICE_PORT=8096

# Run the service
uvicorn main:app --host 0.0.0.0 --port 8096
```

## Architecture

- **Models**: Pydantic models for request/response validation
- **Services**: Core business logic for audio language detection
- **Routers**: FastAPI route handlers
- **Utils**: Triton client and service registry client
- **Middleware**: Rate limiting, error handling, request logging

## Observability

The service exposes metrics at `/enterprise/metrics` endpoint for Prometheus scraping. Metrics include:

- Request duration
- Request count
- Error rates
- Audio processing metrics

## License

MIT

