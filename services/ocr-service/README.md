# OCR Service (Optical Character Recognition)

Microservice for extracting text from images using Surya OCR via Triton Inference Server.

## Features

- **Batch OCR inference** (multiple images per request)
- **ULCA-style request/response schema** consistent with other Dhruva services
- **Surya OCR model** served through Triton (`IMAGE_DATA` → `OUTPUT_TEXT`)
- **Redis + PostgreSQL ready** (for auth, rate limiting, and logging, same pattern as NMT/TTS/ASR)
- **AI4ICore Observability Plugin** integrated for metrics and tracing

## Architecture

```text
Client → API Gateway → OCR Service → Triton Server (Surya OCR)
                             ↓
                        PostgreSQL
                             ↓
                           Redis
```

Layered structure:

- `routers/` – FastAPI routes (`/api/v1/ocr/inference`)
- `services/` – Business logic (`OCRService`)
- `models/` – Pydantic request/response models
- `utils/` – Triton client for Surya OCR
- `middleware/` – Logging, error handling, rate limiting

## Installation

```bash
cd services/ocr-service
pip install -r requirements.txt
cp env.template .env
# edit .env with your DB, Redis, and Triton config
```

## Environment

Key variables (see `env.template` for full list):

- `SERVICE_PORT` – default `8090`
- `DATABASE_URL` – PostgreSQL connection string
- `REDIS_HOST` / `REDIS_PORT` – Redis config
- `TRITON_ENDPOINT` – Surya OCR Triton endpoint (e.g. `http://65.1.35.3:8400`)
- `TRITON_API_KEY` – optional bearer token if your Triton is protected

## API

### 1. OCR Inference

**POST** `/api/v1/ocr/inference`

```json
{
  "image": [
    { "imageContent": "<base64-encoded-image>" },
    { "imageUri": "https://example.com/image.png" }
  ],
  "config": {
    "serviceId": "ai4bharat/surya-ocr-v1--gpu--t4",
    "language": {
      "sourceLanguage": "en",
      "sourceScriptCode": "Latn"
    },
    "textDetection": false
  }
}
```

**Response:**

```json
{
  "output": [
    { "source": "Extracted text from first image", "target": "" },
    { "source": "Extracted text from second image", "target": "" }
  ],
  "config": {
    "serviceId": "ai4bharat/surya-ocr-v1--gpu--t4",
    "language": { "sourceLanguage": "en", "sourceScriptCode": "Latn" },
    "textDetection": false
  }
}
```

Each `source` field is taken from Surya OCR's `full_text` field when `success=true`, otherwise it is an empty string.

## Running

```bash
uvicorn main:app --host 0.0.0.0 --port 8090
```

## Docker

```bash
docker build -t ocr-service:latest -f services/ocr-service/Dockerfile .
docker run -p 8090:8090 --env-file services/ocr-service/.env ocr-service:latest
```

## Next Steps

- Wire OCR request/response logging into PostgreSQL (similar to `nmt_requests` / `nmt_results`).
- Add `AuthProvider` middleware and API key validation once OCR DB schemas are defined.


