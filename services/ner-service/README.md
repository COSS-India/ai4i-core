git# NER Service

Named Entity Recognition microservice for AI4ICore.

This service:
- Exposes a ULCA-style NER endpoint at `/api/v1/ner/inference`
- Forwards requests to a Dhruva NER Triton deployment (model name: `ner`)
- Integrates with the AI4ICore Observability plugin for metrics and dashboards

## API Overview

- **POST** `/api/v1/ner/inference`
  - Request body: `NerInferenceRequest`
    - `config.serviceId`: NER service/model identifier (informational for now)
    - `config.language.sourceLanguage`: language code (e.g., `hi`)
    - `input`: list of objects with `source` text
  - Response body: `NerInferenceResponse`
    - `taskType`: `"ner"`
    - `output`: list of items with:
      - `source`: original input text
      - `nerPrediction`: list of tokens with `token`, `tag`, `tokenIndex`, `tokenStartIndex`, `tokenEndIndex`

## Triton Integration

The service calls a Triton server (default: `65.1.35.3:8300`) with:

- Input tensors:
  - `INPUT_TEXT`: `[[text1], [text2], ...]`
  - `LANG_ID`: `[[lang], [lang], ...]`
- Output tensor:
  - `OUTPUT_TEXT`: JSON-encoded NER predictions

## Configuration

Key environment variables (see `env.template`):

- `SERVICE_NAME` (default: `ner-service`)
- `SERVICE_PORT` (default: `8091`)
- `TRITON_ENDPOINT` (default: `65.1.35.3:8300`)
- `TRITON_API_KEY` (optional)


