# Pipeline Service - Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Prerequisites](#prerequisites)
5. [Installation & Setup](#installation--setup)
6. [Configuration](#configuration)
7. [API Reference](#api-reference)
8. [Pipeline Types](#pipeline-types)
9. [Usage Examples](#usage-examples)
10. [Deployment](#deployment)
11. [Troubleshooting](#troubleshooting)
12. [Development](#development)

---

## Overview

The **Pipeline Service** is a microservice that orchestrates multiple AI tasks in sequence to create complex workflows. It enables multi-stage AI pipelines such as Speech-to-Speech translation (ASR → Translation → TTS) and other combinations of AI services.

### Key Capabilities

- **Multi-task Orchestration**: Chain multiple AI services in sequence
- **Speech-to-Speech Translation**: Complete pipeline from audio input to translated audio output
- **Service Discovery**: Automatic discovery of AI services via service registry
- **Flexible Configuration**: Configurable pipeline tasks and parameters
- **Error Handling**: Robust error handling and retry logic
- **Request Forwarding**: Passes authentication and context through pipeline stages

---

## Architecture

### System Architecture

```
Client → API Gateway → Pipeline Service → ASR Service
                              ↓
                        NMT Service
                              ↓
                        TTS Service
                              ↓
                        Service Registry (Discovery)
```

### Internal Architecture

The service follows a simple orchestration pattern:

```
┌─────────────────────────────────────┐
│         FastAPI Application         │
│  (main.py - Entry Point)            │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────────┐
│   Routers   │  │   Services      │
│             │  │                 │
│ - Pipeline  │  │ - PipelineService│
│ - Health    │  │ - ServiceClient │
└──────┬──────┘  └──────────────────┘
       │
┌──────▼──────┐
│   Utils      │
│             │
│ - HTTPClient│
│ - ServiceRegistryClient│
└─────────────┘
```

### Components

1. **Routers** (`routers/`): FastAPI route handlers
   - `pipeline_router.py`: Pipeline inference endpoints
2. **Services** (`services/`): Business logic
   - `pipeline_service.py`: Pipeline orchestration logic
3. **Utils** (`utils/`): Utility functions
   - `http_client.py`: HTTP client for calling AI services
   - `service_registry_client.py`: Service discovery via registry
4. **Models** (`models/`): Pydantic models
   - `pipeline_request.py`: Request models
   - `pipeline_response.py`: Response models

---

## Features

### Core Features

1. **Pipeline Orchestration**
   - Execute multiple AI tasks in sequence
   - Pass data between pipeline stages
   - Handle errors and retries
   - Support for conditional execution

2. **Supported Task Types**
   - **ASR**: Automatic Speech Recognition (audio → text)
   - **Translation**: Neural Machine Translation (text → text)
   - **TTS**: Text-to-Speech (text → audio)
   - **Transliteration**: Text transliteration (future)

3. **Service Discovery**
   - Automatic discovery of AI services via service registry
   - Fallback to environment variables
   - Health check integration

4. **Request Management**
   - Forward authentication tokens through pipeline
   - Maintain request context
   - Error propagation and handling
   - Timeout management

---

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **Service Registry**: Config service with service registry (optional)
- **AI Services**: ASR, NMT, and TTS services must be available
- **Docker**: Optional, for containerized deployment

### Dependencies

Key Python packages (see `requirements.txt` for complete list):

- `fastapi>=0.104.0`: Web framework
- `uvicorn[standard]>=0.24.0`: ASGI server
- `httpx>=0.25.0`: HTTP client
- `pydantic>=2.5.0`: Data validation
- `python-dotenv>=1.0.0`: Environment variable management

---

## Installation & Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd aiv4-core/services/pipeline-service
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

### 4. Service Discovery Setup

The pipeline service can discover AI services via:
- **Service Registry**: Automatic discovery via config service
- **Environment Variables**: Manual service URL configuration

### 5. Start Service

```bash
# Development
uvicorn main:app --host 0.0.0.0 --port 8090 --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8090 --workers 4
```

### 6. Verify Installation

```bash
curl http://localhost:8090/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "pipeline-service",
  "version": "1.0.0",
  "dependencies": {
    "asr_service": "http://asr-service:8087",
    "nmt_service": "http://nmt-service:8089",
    "tts_service": "http://tts-service:8088"
  }
}
```

---

## Configuration

### Environment Variables

All configuration is done via environment variables. See `env.template` for the complete list.

#### Service Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `pipeline-service` |
| `SERVICE_PORT` | HTTP port | `8090` |
| `SERVICE_HOST` | Service hostname | `pipeline-service` |
| `SERVICE_PUBLIC_URL` | Public-facing URL | - |
| `CONFIG_SERVICE_URL` | Config service URL for registry | `http://config-service:8082` |
| `LOG_LEVEL` | Logging level | `INFO` |

#### AI Service URLs (Optional - for manual configuration)

| Variable | Description | Default |
|----------|-------------|---------|
| `ASR_SERVICE_URL` | ASR service URL (overrides discovery) | - |
| `NMT_SERVICE_URL` | NMT service URL (overrides discovery) | - |
| `TTS_SERVICE_URL` | TTS service URL (overrides discovery) | - |

#### HTTP Client Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HTTP_CLIENT_TIMEOUT` | HTTP client timeout (seconds) | `300` |

#### CORS Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ORIGINS` | CORS allowed origins | `*` |

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
  "service": "pipeline-service",
  "version": "1.0.0",
  "timestamp": 1234567890.123,
  "dependencies": {
    "asr_service": "http://asr-service:8087",
    "asr_service_source": "registry",
    "nmt_service": "http://nmt-service:8089",
    "nmt_service_source": "registry",
    "tts_service": "http://tts-service:8088",
    "tts_service_source": "registry"
  }
}
```

#### 2. Readiness Check

**GET** `/ready`

Kubernetes readiness probe endpoint.

**Response:**
```json
{
  "status": "ready",
  "service": "pipeline-service"
}
```

#### 3. Liveness Check

**GET** `/live`

Kubernetes liveness probe endpoint.

**Response:**
```json
{
  "status": "alive",
  "service": "pipeline-service"
}
```

#### 4. Root Endpoint

**GET** `/`

Get service information.

**Response:**
```json
{
  "name": "Pipeline Service",
  "version": "1.0.0",
  "status": "running",
  "description": "Multi-task AI pipeline orchestration microservice"
}
```

#### 5. Pipeline Info

**GET** `/api/v1/pipeline/info`

Get pipeline service capabilities and usage information.

**Response:**
```json
{
  "service": "pipeline-service",
  "version": "1.0.0",
  "description": "Multi-task AI pipeline orchestration service",
  "supported_task_types": ["asr", "translation", "tts", "transliteration"],
  "example_pipelines": {
    "speech_to_speech": {
      "description": "Full Speech-to-Speech translation pipeline",
      "tasks": [
        {
          "taskType": "asr",
          "description": "Convert audio to text"
        },
        {
          "taskType": "translation",
          "description": "Translate text"
        },
        {
          "taskType": "tts",
          "description": "Convert text to speech"
        }
      ]
    }
  },
  "task_sequence_rules": {
    "asr": ["translation"],
    "translation": ["tts"],
    "transliteration": ["translation", "tts"]
  }
}
```

#### 6. Execute Pipeline Inference

**POST** `/api/v1/pipeline/inference`

Execute a multi-task AI pipeline.

**Headers:**
```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "pipelineTasks": [
    {
      "taskType": "asr",
      "config": {
        "serviceId": "vakyansh-asr-en",
        "language": {
          "sourceLanguage": "en"
        },
        "transcriptionFormat": "transcript"
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
        "language": {
          "sourceLanguage": "hi"
        },
        "gender": "female",
        "samplingRate": 22050
      }
    }
  ],
  "inputData": {
    "audio": [
      {
        "audioContent": "base64EncodedAudioContent..."
      }
    ]
  }
}
```

**Response:**
```json
{
  "pipelineResponse": [
    {
      "taskType": "asr",
      "output": {
        "output": [
          {
            "source": "Hello, how are you?"
          }
        ]
      }
    },
    {
      "taskType": "translation",
      "output": {
        "output": [
          {
            "source": "Hello, how are you?",
            "target": "नमस्ते, आप कैसे हैं?"
          }
        ]
      }
    },
    {
      "taskType": "tts",
      "output": {
        "audio": [
          {
            "audioContent": "base64EncodedAudioContent..."
          }
        ]
      }
    }
  ]
}
```

---

## Pipeline Types

### Speech-to-Speech Translation

Complete pipeline: Audio (English) → Text (English) → Text (Hindi) → Audio (Hindi)

**Use Case**: Real-time voice translation

**Pipeline Tasks**:
1. **ASR**: Convert English audio to text
2. **Translation**: Translate English text to Hindi
3. **TTS**: Convert Hindi text to audio

### Text Translation to Speech

Pipeline: Text (English) → Text (Hindi) → Audio (Hindi)

**Use Case**: Translate text and generate speech

**Pipeline Tasks**:
1. **Translation**: Translate English text to Hindi
2. **TTS**: Convert Hindi text to audio

### Custom Pipelines

You can create custom pipelines by combining available task types in sequence.

---

## Usage Examples

### Python Example - Speech-to-Speech Translation

```python
import requests
import base64

# Read audio file
with open("audio.wav", "rb") as f:
    audio_data = base64.b64encode(f.read()).decode("utf-8")

# Prepare pipeline request
url = "http://localhost:8090/api/v1/pipeline/inference"
headers = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

payload = {
    "pipelineTasks": [
        {
            "taskType": "asr",
            "config": {
                "serviceId": "vakyansh-asr-en",
                "language": {
                    "sourceLanguage": "en"
                }
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
                "language": {
                    "sourceLanguage": "hi"
                },
                "gender": "female"
            }
        }
    ],
    "inputData": {
        "audio": [
            {
                "audioContent": audio_data
            }
        ]
    }
}

# Execute pipeline
response = requests.post(url, json=payload, headers=headers)
result = response.json()

# Extract results
asr_result = result["pipelineResponse"][0]["output"]["output"][0]["source"]
translation_result = result["pipelineResponse"][1]["output"]["output"][0]["target"]
tts_audio = result["pipelineResponse"][2]["output"]["audio"][0]["audioContent"]

print(f"ASR: {asr_result}")
print(f"Translation: {translation_result}")

# Save translated audio
with open("translated_audio.wav", "wb") as f:
    f.write(base64.b64decode(tts_audio))
```

### cURL Example

```bash
curl -X POST http://localhost:8090/api/v1/pipeline/inference \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "pipelineTasks": [
      {
        "taskType": "asr",
        "config": {
          "serviceId": "vakyansh-asr-en",
          "language": {
            "sourceLanguage": "en"
          }
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
          "language": {
            "sourceLanguage": "hi"
          },
          "gender": "female"
        }
      }
    ],
    "inputData": {
      "audio": [
        {
          "audioContent": "base64EncodedAudioContent..."
        }
      ]
    }
  }'
```

---

## Deployment

### Docker Deployment

#### Build Image

```bash
docker build -t pipeline-service:latest .
```

#### Run Container

```bash
docker run -d \
  --name pipeline-service \
  -p 8090:8090 \
  --env-file .env \
  pipeline-service:latest
```

### Production Considerations

1. **Service Discovery**: Ensure service registry is properly configured
2. **Timeout Management**: Set appropriate timeouts for long-running pipelines
3. **Error Handling**: Implement retry logic for transient failures
4. **Monitoring**: Monitor pipeline execution times and failure rates
5. **Scaling**: Use multiple instances behind a load balancer

---

## Troubleshooting

### Common Issues

#### 1. Service Discovery Failed

**Problem**: Cannot discover AI services

**Solutions**:
- Verify service registry is accessible
- Check `CONFIG_SERVICE_URL` is correct
- Use environment variables to manually configure service URLs
- Verify AI services are registered in the registry

#### 2. Pipeline Execution Timeout

**Problem**: Pipeline execution times out

**Solutions**:
- Increase `HTTP_CLIENT_TIMEOUT` value
- Check individual service response times
- Optimize pipeline configuration
- Consider breaking into smaller pipelines

#### 3. Authentication Errors

**Problem**: 401 Unauthorized errors from AI services

**Solutions**:
- Verify API key is valid
- Check API key is passed correctly in Authorization header
- Ensure API key has permissions for all required services

#### 4. Service Unavailable

**Problem**: One or more AI services are unavailable

**Solutions**:
- Check service health endpoints
- Verify service URLs are correct
- Check network connectivity
- Review service logs

---

## Development

### Project Structure

```
pipeline-service/
├── main.py                 # FastAPI application entry point
├── routers/                # API route handlers
│   └── pipeline_router.py
├── services/               # Business logic
│   └── pipeline_service.py
├── models/                 # Pydantic models
│   ├── pipeline_request.py
│   └── pipeline_response.py
├── utils/                  # Utility functions
│   ├── http_client.py
│   └── service_registry_client.py
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


