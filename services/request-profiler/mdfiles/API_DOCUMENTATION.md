# API Documentation - Indian Languages Request Profiler

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, no authentication is required. For production deployment, consider adding:
- API key authentication
- OAuth 2.0
- JWT tokens

## Rate Limiting

- **Default**: 100 requests per minute per IP address
- **Headers**: Rate limit information is included in response headers
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Remaining`: Remaining requests in current window
  - `X-RateLimit-Reset`: Time when the rate limit resets

## Common Headers

### Request Headers

```
Content-Type: application/json
Accept: application/json
```

### Response Headers

```
Content-Type: application/json
X-Request-ID: <uuid>
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
```

## Error Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 400 | Bad Request | Invalid request (business logic error) |
| 422 | Unprocessable Entity | Validation error (invalid input format) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Models not loaded or service not ready |

## Error Response Format

All errors follow this structure:

```json
{
  "error": "error_type",
  "message": "Human-readable error message",
  "details": {
    "field": "specific_field",
    "reason": "detailed_reason"
  },
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-10T12:00:00Z"
}
```

## Endpoints

### 1. Profile Single Text

Profile a single text and get comprehensive analysis.

**Endpoint**: `POST /api/v1/profile`

**Request Body**:

```json
{
  "text": "string (required, 1-50000 chars, min 2 words)",
  "options": {
    "include_entities": "boolean (optional, default: true)",
    "include_language_detection": "boolean (optional, default: true)"
  }
}
```

**Success Response (200 OK)**:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "profile": {
    "domain": {
      "label": "medical",
      "confidence": 0.95,
      "all_scores": {
        "medical": 0.95,
        "legal": 0.02,
        "technical": 0.01,
        "finance": 0.01,
        "casual": 0.005,
        "general": 0.005
      }
    },
    "scores": {
      "complexity_score": 0.42,
      "complexity_level": "MEDIUM",
      "vocabulary_sophistication": 0.65,
      "syntactic_complexity": 0.48,
      "semantic_complexity": 0.35
    },
    "language": {
      "detected_language": "hi",
      "confidence": 0.99,
      "script": "Devanagari"
    },
    "entities": {
      "count": 2,
      "types": ["CONDITION", "URGENCY"],
      "entities": [
        {"text": "हृदयाघात", "type": "CONDITION"},
        {"text": "तत्काल", "type": "URGENCY"}
      ]
    },
    "text_stats": {
      "char_count": 68,
      "word_count": 12,
      "sentence_count": 1,
      "avg_word_length": 5.67,
      "avg_sentence_length": 12.0
    }
  },
  "metadata": {
    "model_version": "2.0.0-indian-languages",
    "processing_time_ms": 45,
    "timestamp": "2026-02-10T12:00:00Z"
  }
}
```

**Example Requests**:

#### Hindi Medical Text

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "रोगी को तीव्र हृदयाघात हुआ है और तत्काल उपचार की आवश्यकता है।",
    "options": {
      "include_entities": true,
      "include_language_detection": true
    }
  }'
```

#### Bengali Legal Text

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "এই চুক্তি উভয় পক্ষের জন্য আইনত বাধ্যতামূলক এবং প্রযোজ্য আইন অনুযায়ী কার্যকর।",
    "options": {
      "include_entities": true
    }
  }'
```

#### Tamil Technical Text

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "சர்வர் உள்ளமைவு கோப்பை புதுப்பிக்கவும் மற்றும் அமைப்புகளை சரிபார்க்கவும்।"
  }'
```

**Validation Errors (422)**:

```json
{
  "detail": [
    {
      "loc": ["body", "text"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Business Logic Errors (400)**:

```json
{
  "error": "validation_error",
  "message": "Text must contain at least 2 words",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-10T12:00:00Z"
}
```

---

### 2. Profile Batch

Profile multiple texts in a single request for improved efficiency.

**Endpoint**: `POST /api/v1/profile/batch`

**Request Body**:

```json
{
  "texts": [
    "string (required, array of 1-100 texts)",
    "string",
    "..."
  ],
  "options": {
    "include_entities": "boolean (optional, default: true)",
    "include_language_detection": "boolean (optional, default: true)"
  }
}
```

**Success Response (200 OK)**:

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440001",
  "profiles": [
    {
      "domain": { /* ... */ },
      "scores": { /* ... */ },
      "language": { /* ... */ },
      "entities": { /* ... */ },
      "text_stats": { /* ... */ }
    },
    {
      "domain": { /* ... */ },
      "scores": { /* ... */ },
      "language": { /* ... */ },
      "entities": { /* ... */ },
      "text_stats": { /* ... */ }
    }
  ],
  "metadata": {
    "model_version": "2.0.0-indian-languages",
    "processing_time_ms": 120,
    "timestamp": "2026-02-10T12:00:00Z",
    "batch_size": 2,
    "successful": 2,
    "failed": 0
  }
}
```

**Example Request**:

```bash
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "रोगी को बुखार और सिरदर्द की शिकायत है।",
      "यह अनुबंध दोनों पक्षों के लिए बाध्यकारी है।",
      "सर्वर कॉन्फ़िगरेशन फ़ाइल को अपडेट करें।"
    ],
    "options": {
      "include_entities": true,
      "include_language_detection": true
    }
  }'
```

**Batch Size Exceeded Error (400)**:

```json
{
  "error": "batch_size_exceeded",
  "message": "Batch size 150 exceeds maximum allowed size of 100",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-10T12:00:00Z"
}
```

---

### 3. Health Check

Check if the service is running and healthy.

**Endpoint**: `GET /api/v1/health`

**Success Response (200 OK)**:

```json
{
  "status": "healthy",
  "models_loaded": true,
  "timestamp": "2026-02-10T12:00:00Z"
}
```

**Example Request**:

```bash
curl http://localhost:8000/api/v1/health
```

---

### 4. Readiness Probe

Kubernetes-style readiness probe to check if the service is ready to accept traffic.

**Endpoint**: `GET /api/v1/health/ready`

**Success Response (200 OK)**:

```json
{
  "status": "ready",
  "models_loaded": true,
  "timestamp": "2026-02-10T12:00:00Z"
}
```

**Service Not Ready (503)**:

```json
{
  "detail": "Models not loaded"
}
```

**Example Request**:

```bash
curl http://localhost:8000/api/v1/health/ready
```

---

### 5. Service Information

Get information about the service version and capabilities.

**Endpoint**: `GET /api/v1/info`

**Success Response (200 OK)**:

```json
{
  "service": "Translation Request Profiler",
  "version": "2.0.0-indian-languages",
  "model_version": "2.0.0",
  "supported_languages": ["hi", "bn", "ta", "te", "kn", "as"],
  "supported_domains": ["medical", "legal", "technical", "finance", "casual", "general"],
  "features": {
    "domain_classification": true,
    "complexity_scoring": true,
    "language_detection": true,
    "entity_extraction": true,
    "batch_processing": true
  },
  "limits": {
    "max_text_length": 50000,
    "max_batch_size": 100,
    "rate_limit_per_minute": 100
  }
}
```

**Example Request**:

```bash
curl http://localhost:8000/api/v1/info
```

---

### 6. Prometheus Metrics

Prometheus-compatible metrics endpoint for monitoring.

**Endpoint**: `GET /metrics`

**Response Format**: Prometheus text format

**Example Response**:

```
# HELP profiler_requests_total Total profile requests
# TYPE profiler_requests_total counter
profiler_requests_total{domain="medical",complexity_level="MEDIUM",status="success"} 42.0
profiler_requests_total{domain="legal",complexity_level="HIGH",status="success"} 18.0

# HELP profiler_latency_seconds Profile request latency in seconds
# TYPE profiler_latency_seconds histogram
profiler_latency_seconds_bucket{le="0.01"} 0.0
profiler_latency_seconds_bucket{le="0.025"} 5.0
profiler_latency_seconds_bucket{le="0.05"} 42.0
profiler_latency_seconds_bucket{le="0.1"} 60.0
profiler_latency_seconds_sum 2.5
profiler_latency_seconds_count 60.0

# HELP profiler_text_length_words Distribution of input text lengths in words
# TYPE profiler_text_length_words histogram
profiler_text_length_words_bucket{le="10.0"} 15.0
profiler_text_length_words_bucket{le="25.0"} 35.0
profiler_text_length_words_bucket{le="50.0"} 50.0
```

**Example Request**:

```bash
curl http://localhost:8000/metrics
```

---

## Data Models

### ProfileRequest

```json
{
  "text": "string (required, 1-50000 chars)",
  "options": {
    "include_entities": "boolean (optional, default: true)",
    "include_language_detection": "boolean (optional, default: true)"
  }
}
```

### BatchProfileRequest

```json
{
  "texts": ["string", "string", "..."],
  "options": {
    "include_entities": "boolean (optional, default: true)",
    "include_language_detection": "boolean (optional, default: true)"
  }
}
```

### DomainPrediction

```json
{
  "label": "medical | legal | technical | finance | casual | general",
  "confidence": "float (0.0-1.0)",
  "all_scores": {
    "medical": "float",
    "legal": "float",
    "technical": "float",
    "finance": "float",
    "casual": "float",
    "general": "float"
  }
}
```

### ComplexityScores

```json
{
  "complexity_score": "float (0.0-1.0)",
  "complexity_level": "LOW | MEDIUM | HIGH",
  "vocabulary_sophistication": "float (0.0-1.0)",
  "syntactic_complexity": "float (0.0-1.0)",
  "semantic_complexity": "float (0.0-1.0)"
}
```

### LanguageDetection

```json
{
  "detected_language": "hi | bn | ta | te | kn | as | ...",
  "confidence": "float (0.0-1.0)",
  "script": "Devanagari | Bengali | Tamil | Telugu | Kannada | Assamese | ..."
}
```

### EntityInfo

```json
{
  "count": "integer",
  "types": ["string", "..."],
  "entities": [
    {
      "text": "string",
      "type": "string",
      "start": "integer (optional)",
      "end": "integer (optional)"
    }
  ]
}
```

### TextStats

```json
{
  "char_count": "integer",
  "word_count": "integer",
  "sentence_count": "integer",
  "avg_word_length": "float",
  "avg_sentence_length": "float"
}
```

---

## Usage Examples

### Python

```python
import requests

# Single text profiling
response = requests.post(
    "http://localhost:8000/api/v1/profile",
    json={
        "text": "रोगी को तीव्र हृदयाघात हुआ है।",
        "options": {
            "include_entities": True,
            "include_language_detection": True
        }
    }
)

if response.status_code == 200:
    result = response.json()
    print(f"Domain: {result['profile']['domain']['label']}")
    print(f"Complexity: {result['profile']['scores']['complexity_level']}")
    print(f"Language: {result['profile']['language']['detected_language']}")
else:
    print(f"Error: {response.status_code} - {response.text}")
```

### JavaScript (Node.js)

```javascript
const axios = require('axios');

async function profileText(text) {
  try {
    const response = await axios.post('http://localhost:8000/api/v1/profile', {
      text: text,
      options: {
        include_entities: true,
        include_language_detection: true
      }
    });

    const profile = response.data.profile;
    console.log(`Domain: ${profile.domain.label}`);
    console.log(`Complexity: ${profile.scores.complexity_level}`);
    console.log(`Language: ${profile.language.detected_language}`);
  } catch (error) {
    console.error(`Error: ${error.response.status} - ${error.response.data}`);
  }
}

profileText('रोगी को तीव्र हृदयाघात हुआ है।');
```

### cURL

```bash
# Single text profiling
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "रोगी को तीव्र हृदयाघात हुआ है।"}'

# Batch profiling
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["रोगी को बुखार है।", "यह अनुबंध बाध्यकारी है।"]}'

# Health check
curl http://localhost:8000/api/v1/health

# Service info
curl http://localhost:8000/api/v1/info
```

---

## Best Practices

1. **Use Batch Endpoint for Multiple Texts**: More efficient than multiple single requests
2. **Disable Unnecessary Features**: Set `include_entities: false` if you don't need entity extraction
3. **Handle Rate Limits**: Implement exponential backoff when receiving 429 errors
4. **Monitor Response Times**: Use the `/metrics` endpoint to track performance
5. **Validate Input Client-Side**: Check text length and word count before sending
6. **Use Request IDs for Debugging**: Include request_id in error reports
7. **Cache Results**: Consider caching results for identical texts
8. **Set Timeouts**: Configure appropriate timeouts for your HTTP client

---

**Version**: 2.0.0-indian-languages
**Last Updated**: 2026-02-10


