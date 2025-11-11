# API Documentation

## Overview

Comprehensive API reference for ASR, TTS, and NMT microservices.

## Base URLs

- **API Gateway**: `http://localhost:8080` (production: `https://api.dhruva-platform.com`)
- **ASR Service**: `http://localhost:8087` (direct access, not recommended)
- **TTS Service**: `http://localhost:8088` (direct access, not recommended)
- **NMT Service**: `http://localhost:8089` (direct access, not recommended)

## Authentication

**API Key Authentication**: All endpoints require API key in Authorization header.

**Header Format**:

```
Authorization: Bearer YOUR_API_KEY
```

**Rate Limits**:

- 60 requests per minute per API key
- 1000 requests per hour per API key
- 10000 requests per day per API key

## ASR Service API

### POST /api/v1/asr/inference

**Description**: Convert speech to text (batch inference)

**Request Body**:

```json
{
  "audio": [{ "audioContent": "base64_encoded_audio_data" }],
  "config": {
    "language": { "sourceLanguage": "en" },
    "serviceId": "vakyansh-asr-en",
    "audioFormat": "wav",
    "samplingRate": 16000
  }
}
```

**Response** (200 OK):

```json
{
  "output": [{ "source": "Hello, this is a test transcription." }]
}
```

**Error Responses**:

- 401: Invalid or missing API key
- 422: Invalid audio format or configuration
- 429: Rate limit exceeded
- 503: Service unavailable

#### GET /api/v1/asr/models

**Description**: List available ASR models

**Response** (200 OK):

```json
{
  "models": [
    {
      "model_id": "vakyansh-asr-en",
      "languages": ["en"],
      "description": "English ASR model"
    }
  ]
}
```

#### WebSocket /socket.io/asr

**Description**: Real-time speech-to-text streaming

**Connection Parameters**:

- `serviceId`: ASR model identifier (required)
- `language`: Language code (required)
- `samplingRate`: Audio sample rate in Hz (required)
- `apiKey`: API key for authentication (optional)

**Events**:

- Client → Server: `start`, `data`, `disconnect`
- Server → Client: `ready`, `response`, `error`, `terminate`

**Example** (Python):

```python
import socketio
sio = socketio.Client()
sio.connect('http://localhost:8087/socket.io/asr?serviceId=vakyansh-asr-en&language=en&samplingRate=16000&apiKey=YOUR_API_KEY')
sio.emit('start')
sio.emit('data', {'audioData': audio_bytes, 'isSpeaking': True, 'disconnectStream': False})
```

## TTS Service API

### POST /api/v1/tts/inference

**Description**: Convert text to speech (batch inference)

**Request Body**:

```json
{
  "input": [{ "source": "Hello world" }],
  "config": {
    "language": { "sourceLanguage": "en" },
    "serviceId": "indic-tts-coqui-misc",
    "gender": "female",
    "audioFormat": "wav",
    "samplingRate": 22050
  }
}
```

**Response** (200 OK):

```json
{
  "audio": [{ "audioContent": "base64_encoded_audio_data" }],
  "config": {
    "audioFormat": "wav",
    "samplingRate": 22050,
    "audioDuration": 3.5
  }
}
```

#### GET /api/v1/tts/voices

**Description**: List available TTS voices

**Query Parameters**:

- `language`: Filter by language code (optional)
- `gender`: Filter by gender (male/female) (optional)

**Response** (200 OK):

```json
{
  "voices": [
    {
      "voice_id": "indic-tts-coqui-dravidian-female",
      "name": "Dravidian Female Voice",
      "gender": "female",
      "languages": ["kn", "ml", "ta", "te"],
      "model_id": "indic-tts-coqui-dravidian"
    }
  ],
  "total": 6,
  "filtered": 2
}
```

#### WebSocket /socket.io/tts

**Description**: Real-time text-to-speech streaming

**Connection Parameters**:

- `serviceId`: TTS model identifier (required)
- `voice_id`: Voice identifier (required)
- `language`: Language code (required)
- `gender`: Voice gender (required)
- `audioFormat`: Output format (optional, default: wav)
- `apiKey`: API key for authentication (optional)

**Events**:

- Client → Server: `start`, `data`, `disconnect`
- Server → Client: `ready`, `response`, `error`, `terminate`

## NMT Service API

### POST /api/v1/nmt/inference

**Description**: Translate text between languages (batch inference, max 90 texts)

**Request Body**:

```json
{
  "input": [{ "source": "Hello world" }],
  "config": {
    "language": {
      "sourceLanguage": "en",
      "targetLanguage": "hi"
    },
    "serviceId": "indictrans-v2-all"
  }
}
```

**Response** (200 OK):

```json
{
  "output": [
    {
      "source": "Hello world",
      "target": "नमस्ते दुनिया"
    }
  ]
}
```

#### GET /api/v1/nmt/models

**Description**: List available NMT models and language pairs

**Response** (200 OK):

```json
{
  "models": [
    {
      "model_id": "indictrans-v2-all",
      "language_pairs": [
        { "source": "en", "target": "hi" },
        { "source": "hi", "target": "en" }
      ],
      "description": "IndicTrans2 model supporting all Indic languages"
    }
  ]
}
```

## Interactive API Documentation

Each service provides interactive Swagger UI documentation:

- **ASR Service**: http://localhost:8087/docs
- **TTS Service**: http://localhost:8088/docs
- **NMT Service**: http://localhost:8089/docs
- **API Gateway**: http://localhost:8080/docs (aggregated)

## OpenAPI Specifications

Download OpenAPI JSON specs:

- **ASR Service**: http://localhost:8087/openapi.json
- **TTS Service**: http://localhost:8088/openapi.json
- **NMT Service**: http://localhost:8089/openapi.json

## Error Response Format

All services return consistent error responses:

```json
{
  "detail": {
    "message": "Error description",
    "code": "ERROR_CODE",
    "timestamp": 1234567890.123
  }
}
```

**Common Error Codes**:

- `AUTHENTICATION_ERROR` (401): Invalid or missing API key
- `AUTHORIZATION_ERROR` (403): Insufficient permissions
- `RATE_LIMIT_EXCEEDED` (429): Too many requests
- `VALIDATION_ERROR` (422): Invalid request payload
- `INTERNAL_ERROR` (500): Server error

## Supported Languages

All services support 22+ Indic languages:

- English (en), Hindi (hi), Tamil (ta), Telugu (te), Kannada (kn), Malayalam (ml), Bengali (bn), Gujarati (gu), Marathi (mr), Punjabi (pa), Oriya (or), Assamese (as), Urdu (ur), Sanskrit (sa), Kashmiri (ks), Nepali (ne), Sindhi (sd), Konkani (kok), Dogri (doi), Maithili (mai), Bodo (brx), Manipuri (mni)
