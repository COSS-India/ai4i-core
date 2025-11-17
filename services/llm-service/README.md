# LLM Service

Large Language Model microservice for text processing, translation, and generation. Supports multiple Indic languages.

## Features

- LLM inference for text processing and translation
- Support for multiple Indic languages
- Batch processing support
- Database logging for requests and results
- Rate limiting and authentication support
- Health check endpoints

## API Endpoints

### Inference

- `POST /api/v1/llm/inference` - Perform LLM inference
- `GET /api/v1/llm/models` - List available LLM models
- `GET /api/v1/llm/health` - Health check
- `GET /api/v1/llm/ready` - Readiness check
- `GET /api/v1/llm/live` - Liveness check

## Request Format

```json
{
  "input": [
    {
      "source": "Hello how are you"
    }
  ],
  "config": {
    "serviceId": "llm",
    "inputLanguage": "en",
    "outputLanguage": "hi"
  }
}
```

## Response Format

```json
{
  "output": [
    {
      "source": "Hello how are you",
      "target": "नमस्ते, आप कैसे हैं?"
    }
  ]
}
```

## Configuration

The service connects to a Triton inference server endpoint at `http://13.220.11.146:8000/services/inference/llm`.

Set `TRITON_ENDPOINT` in the `.env` file to configure the endpoint URL.

## Supported Languages

- English (en)
- Hindi (hi)
- Tamil (ta)
- Telugu (te)
- Kannada (kn)
- Malayalam (ml)
- Bengali (bn)
- Gujarati (gu)
- Marathi (mr)
- Punjabi (pa)
- Odia (or)
- Assamese (as)
- Urdu (ur)

## Port

The service runs on port `8090` internally and is exposed on port `8093` externally.
