# Smart Router Service

Intelligent routing service for the AI4I platform that evaluates policies and routes requests to appropriate services.

## Features

- Policy-based routing using Policy Engine
- Support for multiple service types (ASR, NMT, TTS, LLM, Pipeline)
- Automatic service discovery and routing
- Request forwarding with authentication headers

## API Endpoints

### POST `/api/v1/smart-router/route`

Smart route a request to the appropriate service based on policy evaluation.

**Request:**
```json
{
  "user_id": "user123",
  "tenant_id": "tenant-abc",
  "service_type": "tts",
  "input_data": {
    "input": [{"source": "नमस्ते"}]
  },
  "config": {
    "serviceId": "indic-tts-coqui-indo_aryan",
    "language": {"sourceLanguage": "hi"},
    "gender": "female"
  },
  "latency_policy": "medium",
  "cost_policy": "tier_2",
  "accuracy_policy": "standard"
}
```

**Response:**
```json
{
  "routed": true,
  "service_url": "http://tts-service:8088/api/v1/tts/inference",
  "policy_id": "pol_standard_balanced",
  "routing_flags": {
    "model_family": "general",
    "model_variant": "standard",
    "priority": 5
  },
  "response": {
    "output": [{"audioContent": "base64..."}]
  }
}
```

### GET `/health`

Health check endpoint.

## Configuration

See `env.template` for environment variables.

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Run service
python smart-router.py
```

Or using Docker:
```bash
docker build -t smart-router .
docker run -p 8096:8096 smart-router
```
