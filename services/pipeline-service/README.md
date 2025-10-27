# Pipeline Service

Microservice for orchestrating multi-task AI pipelines. Enables chaining of AI services in sequence (e.g., Speech-to-Speech translation: ASR → Translation → TTS).

## Features

- **Multi-task pipeline orchestration** - Chain multiple AI services in sequence
- **Speech-to-Speech translation** - Full pipeline from audio input to audio output
- **Automatic format conversion** - Transforms outputs between stages automatically
- **Task sequencing validation** - Ensures valid task sequences
- **Error handling** - Comprehensive error handling at each stage
- **Logging** - Detailed logging for each pipeline stage

## Architecture

```
Client → API Gateway → Pipeline Service → ASR Service
                                ↓
                          NMT Service
                                ↓
                          TTS Service
```

The pipeline service orchestrates the execution of multiple AI tasks:
1. Receives pipeline request with task sequence
2. Calls each service in sequence
3. Transforms outputs between tasks
4. Returns all intermediate results

## Prerequisites

- Python 3.11+
- ASR, NMT, and TTS services running
- Docker (optional)

## Installation

1. **Clone repository**
   ```bash
   cd services/pipeline-service
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

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_PORT` | Service port | 8090 |
| `ASR_SERVICE_URL` | ASR service URL | http://asr-service:8087 |
| `NMT_SERVICE_URL` | NMT service URL | http://nmt-service:8089 |
| `TTS_SERVICE_URL` | TTS service URL | http://tts-service:8088 |
| `HTTP_CLIENT_TIMEOUT` | HTTP client timeout in seconds | 300 |
| `LOG_LEVEL` | Log level | INFO |

## Usage

### Start Service

```bash
uvicorn main:app --host 0.0.0.0 --port 8090
```

Or using Docker:

```bash
docker-compose up pipeline-service
```

### API Endpoints

#### 1. Execute Pipeline Inference

**POST** `/api/v1/pipeline/inference`

Execute a multi-task AI pipeline.

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
        "gender": "male"
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
      "serviceId": "vakyansh-asr-en",
      "output": [
        {
          "source": "Hello world"
        }
      ]
    },
    {
      "taskType": "translation",
      "serviceId": "indictrans-v2-all",
      "output": [
        {
          "source": "Hello world",
          "target": "नमस्ते दुनिया"
        }
      ]
    },
    {
      "taskType": "tts",
      "serviceId": "indic-tts-coqui-dravidian",
      "output": [
        {
          "audioContent": "base64EncodedAudio..."
        }
      ],
      "config": {
        "language": {
          "sourceLanguage": "hi"
        },
        "audioFormat": "wav"
      }
    }
  ]
}
```

#### 2. Get Service Information

**GET** `/api/v1/pipeline/info`

Get pipeline service capabilities and usage information.

#### 3. Health Checks

- **GET** `/health` - Overall service health
- **GET** `/ready` - Readiness check
- **GET** `/live` - Liveness check

## Supported Pipeline Types

### 1. Speech-to-Speech Translation

Chain: ASR → Translation → TTS

Converts speech in one language to speech in another language.

**Example:**
```json
{
  "pipelineTasks": [
    {"taskType": "asr", "config": {...}},
    {"taskType": "translation", "config": {...}},
    {"taskType": "tts", "config": {...}}
  ],
  "inputData": {
    "audio": [{"audioContent": "..."}]
  }
}
```

### 2. Text-to-Speech Translation

Chain: Translation → TTS

Translates text and converts it to speech.

**Example:**
```json
{
  "pipelineTasks": [
    {"taskType": "translation", "config": {...}},
    {"taskType": "tts", "config": {...}}
  ],
  "inputData": {
    "input": [{"source": "Hello"}]
  }
}
```

## Task Sequencing Rules

| Current Task | Next Task |
|--------------|-----------|
| ASR | Translation only |
| Translation | TTS only |
| Transliteration | Translation or TTS (sentence-level only) |

## Data Flow

### ASR → Translation

- **Input**: Audio content (base64)
- **ASR Output**: Text transcript
- **Translation Input**: Transform transcript to text input format

### Translation → TTS

- **Input**: Source text
- **Translation Output**: Target text
- **TTS Input**: Transform target to source (use translated text as TTS source)

### TTS

- **Input**: Text
- **Output**: Audio content (base64)
- **Config**: Returns audio format and language configuration

## Error Handling

The service provides comprehensive error handling:

- **Validation errors** (400): Invalid task sequence, missing required fields
- **Service errors** (500): Errors from ASR/NMT/TTS services
- **Pipeline errors**: Intermediate task failures stop the pipeline

## Example Usage

### Python Client

```python
import requests
import base64

# Read audio file
with open('audio.wav', 'rb') as f:
    audio_content = base64.b64encode(f.read()).decode('utf-8')

# Create pipeline request
request = {
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
        "audio": [{"audioContent": audio_content}]
    }
}

# Execute pipeline
response = requests.post(
    'http://localhost:8090/api/v1/pipeline/inference',
    json=request,
    headers={'Authorization': 'Bearer YOUR_API_KEY'}
)

print(response.json())
```

## API Gateway Integration

The pipeline service is integrated with the API Gateway at route:

- `/api/v1/pipeline/*` → `pipeline-service`

All requests are routed through the API Gateway for authentication and rate limiting.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

```
pipeline-service/
├── main.py                 # FastAPI application
├── routers/
│   └── pipeline_router.py # API routes
├── services/
│   └── pipeline_service.py # Pipeline orchestration logic
├── models/
│   ├── pipeline_request.py  # Request models
│   └── pipeline_response.py # Response models
├── utils/
│   └── http_client.py      # HTTP client for calling services
└── requirements.txt
```

## Contributing

Contributions are welcome! Please read the contributing guidelines in the main repository.

## License

MIT License
