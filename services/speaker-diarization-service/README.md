# Speaker Diarization Service

Speaker Diarization microservice for identifying different speakers in audio and returning their segments.

## Overview

This service provides speaker diarization capabilities using Triton Inference Server. It processes audio files and identifies different speakers, returning segments with speaker labels and timestamps.

## Features

- **Batch Processing**: Process multiple audio files in a single request
- **Flexible Input**: Support for base64-encoded audio content or audio URIs
- **Triton Integration**: Uses Triton Inference Server for model inference
- **Observability**: Integrated with AI4ICore Observability Plugin for metrics and tracing
- **Rate Limiting**: Redis-based rate limiting per API key
- **Service Registry**: Automatic registration with central service registry

## API Endpoints

### POST `/api/v1/speaker-diarization/inference`

Perform speaker diarization inference on audio files.

**Request Body:**
```json
{
  "controlConfig": {
    "dataTracking": true
  },
  "config": {
    "serviceId": "ai4bharat/speaker-diarization"
  },
  "audio": [
    {
      "audioContent": "base64-encoded-audio-string",
      "audioUri": "https://example.com/audio.wav"
    }
  ]
}
```

**Response:**
```json
{
  "taskType": "speaker-diarization",
  "output": [
    {
      "total_segments": 4,
      "num_speakers": 3,
      "speakers": [
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_02"
      ],
      "segments": [
        {
          "start_time": 4.01,
          "end_time": 6.83,
          "duration": 2.82,
          "speaker": "SPEAKER_00"
        }
      ]
    }
  ],
  "config": {
    "serviceId": "ai4bharat/speaker-diarization",
    "language": null
  }
}
```

### GET `/health`

Health check endpoint for service and dependencies.

### GET `/`

Root endpoint returning service information.

## Configuration

See `env.template` for available environment variables. Key configurations:

- `TRITON_ENDPOINT`: Triton Inference Server endpoint
- `TRITON_API_KEY`: Optional API key for Triton authentication
- `SERVICE_PORT`: Service port (default: 8095)
- `REDIS_HOST`, `REDIS_PORT`: Redis configuration for rate limiting
- `DATABASE_URL`: PostgreSQL connection string

## Development

### Local Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e ../../libs/ai4icore_observability
```

2. Set environment variables (copy from `env.template`)

3. Run the service:
```bash
uvicorn main:app --host 0.0.0.0 --port 8095
```

### Docker Build

```bash
docker build -t speaker-diarization-service:latest .
```

### Docker Run

```bash
docker run -p 8095:8095 \
  -e TRITON_ENDPOINT=your-triton-endpoint \
  -e REDIS_HOST=redis \
  -e DATABASE_URL=postgresql+asyncpg://... \
  speaker-diarization-service:latest
```

## Architecture

- **Models**: Pydantic models for request/response validation
- **Services**: Core business logic for speaker diarization inference
- **Routers**: FastAPI route handlers
- **Utils**: Triton client and service registry utilities
- **Middleware**: Rate limiting, error handling, request logging

## Observability

The service integrates with AI4ICore Observability Plugin for:
- Request metrics (latency, payload size, error rate)
- Prometheus metrics endpoint at `/enterprise/metrics`
- Automatic audio length tracking for speaker diarization

## License

MIT

