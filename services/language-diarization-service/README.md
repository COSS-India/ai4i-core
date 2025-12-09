# Language Diarization Service

Language Diarization microservice for identifying different languages in audio and returning their segments with confidence scores.

## Overview

This service provides language diarization inference capabilities using Triton Inference Server. It processes audio files and identifies language segments with timestamps and confidence scores.

## Features

- **Language Diarization**: Identifies different languages in audio files
- **Batch Processing**: Supports processing multiple audio files in a single request
- **Confidence Scores**: Returns confidence scores for each detected language segment
- **Triton Integration**: Uses Triton Inference Server for model inference
- **Observability**: Integrated with AI4ICore Observability Plugin for metrics and monitoring
- **Rate Limiting**: Redis-based rate limiting per API key
- **Service Registry**: Automatic registration with the service registry

## API Endpoints

### POST `/api/v1/language-diarization/inference`

Perform language diarization inference on one or more audio files.

**Request Body:**
```json
{
  "controlConfig": {
    "dataTracking": true
  },
  "config": {
    "serviceId": "ai4bharat/language-diarization"
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
  "taskType": "language-diarization",
  "output": [
    {
      "total_segments": 11,
      "segments": [
        {
          "start_time": 0,
          "end_time": 2,
          "duration": 2,
          "language": "nn: Norwegian Nynorsk",
          "confidence": 0.2673
        }
      ],
      "target_language": "all"
    }
  ],
  "config": {
    "serviceId": "ai4bharat/language-diarization"
  }
}
```

### GET `/health`

Health check endpoint that verifies Redis, PostgreSQL, and Triton connectivity.

## Configuration

See `env.template` for all available environment variables.

### Key Configuration Variables

- `TRITON_ENDPOINT`: Triton Inference Server endpoint (default: `65.1.35.3:8600`)
- `SERVICE_PORT`: Service port (default: `8094`)
- `REDIS_HOST`: Redis host for rate limiting
- `DATABASE_URL`: PostgreSQL connection string

## Running the Service

### Using Docker Compose

The service is included in `docker-compose.yml`:

```bash
docker compose up language-diarization-service
```

### Standalone

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ../../libs/ai4icore_observability

# Set environment variables
export TRITON_ENDPOINT=65.1.35.3:8600
export SERVICE_PORT=8094

# Run the service
uvicorn main:app --host 0.0.0.0 --port 8094
```

## Architecture

- **Models**: Pydantic models for request/response validation
- **Services**: Core business logic for language diarization
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

