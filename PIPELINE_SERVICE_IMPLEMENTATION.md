# Pipeline Service Implementation Summary

## Overview

Successfully implemented a Pipeline Service for the aiv4-core microservices architecture. This service orchestrates multi-task AI pipelines, enabling sequential execution of AI services (ASR, Translation, TTS) as a single workflow.

## What Was Implemented

### 1. Core Service Structure
- **Directory**: `services/pipeline-service/`
- **Language**: Python 3.11+ with FastAPI
- **Port**: 8090

### 2. Key Components

#### Models (`models/`)
- `pipeline_request.py` - Request models for pipeline execution
  - `PipelineTask` - Task configuration
  - `TaskType` - Supported task types (ASR, Translation, TTS, Transliteration)
  - `PipelineInferenceRequest` - Main request model with validation
- `pipeline_response.py` - Response models
  - `PipelineInferenceResponse` - Complete pipeline output
  - `PipelineTaskOutput` - Individual task outputs

#### Services (`services/`)
- `pipeline_service.py` - Main orchestration logic
  - Executes tasks sequentially
  - Transforms outputs between tasks
  - Handles errors and logging

#### Utilities (`utils/`)
- `http_client.py` - HTTP client for calling ASR, NMT, and TTS services
  - Async HTTP requests
  - Service URL configuration
  - Error handling

#### Routers (`routers/`)
- `pipeline_router.py` - API endpoints
  - `POST /api/v1/pipeline/inference` - Execute pipeline
  - `GET /api/v1/pipeline/info` - Service information

#### Main Application
- `main.py` - FastAPI application entry point
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration
- `README.md` - Comprehensive documentation

### 3. Key Features

#### Pipeline Types Supported
1. **Speech-to-Speech Translation**: ASR → Translation → TTS
2. **Text-to-Speech Translation**: Translation → TTS
3. **Custom Pipelines**: Any valid sequence of supported tasks

#### Task Sequencing Rules
- ASR can only be followed by Translation
- Translation can only be followed by TTS
- Transliteration can be followed by Translation or TTS (sentence-level only)

#### Data Transformation
- **ASR → Translation**: Audio → Text → Text Input Format
- **Translation → TTS**: Target text → Source text (reversed for TTS)
- Automatic format conversion between stages

### 4. Integration Points

#### Docker Compose
Added to `docker-compose.yml`:
```yaml
pipeline-service:
  build: ./services/pipeline-service
  ports:
    - "8090:8090"
  depends_on:
    - asr-service
    - nmt-service
    - tts-service
```

#### API Gateway
Updated `services/api-gateway-service/main.py`:
- Added route: `/api/v1/pipeline` → `pipeline-service`
- Added service URL mapping

## Usage Example

### Request
```json
{
  "pipelineTasks": [
    {
      "taskType": "asr",
      "config": {
        "serviceId": "vakyansh-asr-en",
        "language": {"sourceLanguage": "en"}
      }
    },
    {
      "taskType": "translation",
      "config": {
        "serviceId": "indictrans-v2-all",
        "language": {
          "sourceLanguage": "en",
          "targetLanguage": "hi"
        }
      }
    },
    {
      "taskType": "tts",
      "config": {
        "serviceId": "indic-tts-coqui-dravidian",
        "language": {"sourceLanguage": "hi"},
        "gender": "male"
      }
    }
  ],
  "inputData": {
    "audio": [
      {
        "audioContent": "base64EncodedAudio..."
      }
    ]
  }
}
```

### Response
```json
{
  "pipelineResponse": [
    {
      "taskType": "asr",
      "serviceId": "vakyansh-asr-en",
      "output": [{"source": "Hello world"}]
    },
    {
      "taskType": "translation",
      "serviceId": "indictrans-v2-all",
      "output": [{"source": "Hello world", "target": "नमस्ते दुनिया"}]
    },
    {
      "taskType": "tts",
      "serviceId": "indic-tts-coqui-dravidian",
      "output": [{"audioContent": "base64EncodedAudio..."}],
      "config": {"language": {"sourceLanguage": "hi"}}
    }
  ]
}
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/pipeline/inference` | Execute multi-task pipeline |
| GET | `/api/v1/pipeline/info` | Get service capabilities |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness check |
| GET | `/live` | Liveness check |

## Architecture Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ API Gateway │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Pipeline Service│
└──────┬──────────┘
       │
       ├─► ASR Service (audio → text)
       │
       ├─► NMT Service (text → text)
       │
       └─► TTS Service (text → audio)
       │
       ▼
┌─────────────┐
│   Response  │
└─────────────┘
```

## Testing

To test the pipeline service:

1. Start all services:
```bash
docker-compose up
```

2. Send a pipeline request:
```bash
curl -X POST http://localhost:8090/api/v1/pipeline/inference \
  -H "Content-Type: application/json" \
  -d '{
    "pipelineTasks": [
      {
        "taskType": "asr",
        "config": {
          "serviceId": "vakyansh-asr-en",
          "language": {"sourceLanguage": "en"}
        }
      },
      {
        "taskType": "translation",
        "config": {
          "serviceId": "indictrans-v2-all",
          "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
        }
      },
      {
        "taskType": "tts",
        "config": {
          "serviceId": "indic-tts-coqui-dravidian",
          "language": {"sourceLanguage": "hi"},
          "gender": "male"
        }
      }
    ],
    "inputData": {
      "audio": [{"audioContent": "YOUR_BASE64_AUDIO"}]
    }
  }'
```

## Files Created

```
services/pipeline-service/
├── main.py
├── requirements.txt
├── Dockerfile
├── env.template
├── README.md
├── models/
│   ├── __init__.py
│   ├── pipeline_request.py
│   └── pipeline_response.py
├── services/
│   ├── __init__.py
│   └── pipeline_service.py
├── routers/
│   ├── __init__.py
│   └── pipeline_router.py
└── utils/
    ├── __init__.py
    └── http_client.py
```

## Next Steps

1. **Testing**: Add unit tests and integration tests
2. **Monitoring**: Add metrics and observability
3. **Error Recovery**: Implement retry mechanisms
4. **Caching**: Add response caching for repeated requests
5. **Streaming**: Support streaming for long-running pipelines

## Dependencies

- FastAPI
- httpx
- pydantic
- uvicorn

## Environment Variables

- `SERVICE_PORT` (default: 8090)
- `ASR_SERVICE_URL`
- `NMT_SERVICE_URL`
- `TTS_SERVICE_URL`
- `HTTP_CLIENT_TIMEOUT` (default: 300 seconds)

## Documentation

Full documentation available in `services/pipeline-service/README.md`

