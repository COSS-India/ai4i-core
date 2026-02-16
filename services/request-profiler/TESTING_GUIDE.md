# Request Profiler API Testing Guide

## Service Status

✅ **Service is running and healthy!**

- **Base URL**: `http://localhost:8888`
- **Container**: `request-profiler`
- **Status**: Models loaded and ready

## Quick Start

The service is already running via Docker. You can test it immediately using the examples below.

## Available APIs

### 1. Health Check
**Endpoint**: `GET /api/v1/health`

Check if the service is running and models are loaded.

```bash
curl http://localhost:8888/api/v1/health
```

**Expected Response**:
```json
{
    "status": "healthy",
    "models_loaded": true,
    "timestamp": "2026-02-16T04:29:21.315975Z"
}
```

---

### 2. Readiness Probe
**Endpoint**: `GET /api/v1/health/ready`

Kubernetes-style readiness check (returns 503 if models not loaded).

```bash
curl http://localhost:8888/api/v1/health/ready
```

---

### 3. Service Information
**Endpoint**: `GET /api/v1/info`

Get service version, capabilities, and limits.

```bash
curl http://localhost:8888/api/v1/info
```

**Expected Response**:
```json
{
    "service_name": "Translation Request Profiler",
    "service_version": "1.0.0",
    "model_version": "...",
    "uptime_seconds": 123.45,
    "models_loaded": true
}
```

---

### 4. Profile Single Text
**Endpoint**: `POST /api/v1/profile`

Profile a single text to get domain classification, complexity scores, language detection, and entity extraction.

```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Patient has fever and headache. Temperature: 102°F. Prescription: Paracetamol.",
    "options": {
      "include_entities": true,
      "include_language_detection": true
    }
  }'
```

**Example with Hindi text**:
```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "रोगी को तीव्र हृदयाघात हुआ है और तत्काल उपचार की आवश्यकता है।"
  }'
```

**Response includes**:
- `domain`: Classification (medical, legal, technical, finance, casual, general)
- `scores`: Complexity scores and levels
- `language`: Detected language and confidence
- `entities`: Extracted entities (if enabled)
- `text_stats`: Character, word, sentence counts

---

### 5. Batch Profiling
**Endpoint**: `POST /api/v1/profile/batch`

Profile multiple texts in a single request (more efficient than multiple single requests).

```bash
curl -X POST http://localhost:8888/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Hello world this is a test",
      "The quick brown fox jumps over the lazy dog",
      "Medical terminology and complex pharmaceutical interactions"
    ],
    "options": {
      "include_entities": true,
      "include_language_detection": true
    }
  }'
```

**Maximum batch size**: 100 texts

---

### 6. Prometheus Metrics
**Endpoint**: `GET /metrics`

Get Prometheus-compatible metrics for monitoring.

```bash
curl http://localhost:8888/metrics
```

---

### 7. Interactive API Documentation
**Endpoint**: `GET /docs`

Open in browser: `http://localhost:8888/docs`

FastAPI automatically generates interactive Swagger UI documentation where you can:
- See all available endpoints
- Test APIs directly from the browser
- View request/response schemas
- Try out different parameters

---

## Testing Examples

### Test 1: Simple Health Check
```bash
curl http://localhost:8888/api/v1/health
```

### Test 2: Profile English Medical Text
```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient has fever. Temperature: 102°F. Prescription: Paracetamol."}'
```

### Test 3: Profile Hindi Text
```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "रोगी को बुखार और सिरदर्द की शिकायत है।"}'
```

### Test 4: Batch Processing
```bash
curl -X POST http://localhost:8888/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Simple text here",
      "Complex medical terminology with pharmaceutical interactions"
    ]
  }'
```

### Test 5: Service Info
```bash
curl http://localhost:8888/api/v1/info
```

---

## Python Testing Example

```python
import requests

BASE_URL = "http://localhost:8888/api/v1"

# Health check
response = requests.get(f"{BASE_URL}/health")
print("Health:", response.json())

# Profile single text
response = requests.post(
    f"{BASE_URL}/profile",
    json={
        "text": "Patient has fever and headache. Temperature: 102°F.",
        "options": {
            "include_entities": True,
            "include_language_detection": True
        }
    }
)
result = response.json()
print(f"Domain: {result['profile']['domain']['label']}")
print(f"Complexity: {result['profile']['scores']['complexity_level']}")
print(f"Language: {result['profile']['language']['detected_language']}")

# Batch profiling
response = requests.post(
    f"{BASE_URL}/profile/batch",
    json={
        "texts": [
            "Simple text",
            "Complex medical terminology"
        ]
    }
)
print("Batch results:", len(response.json()["profiles"]), "profiles")
```

---

## JavaScript/Node.js Testing Example

```javascript
const axios = require('axios');

const BASE_URL = 'http://localhost:8888/api/v1';

async function testAPI() {
  // Health check
  const health = await axios.get(`${BASE_URL}/health`);
  console.log('Health:', health.data);

  // Profile text
  const profile = await axios.post(`${BASE_URL}/profile`, {
    text: 'Patient has fever and headache.',
    options: {
      include_entities: true,
      include_language_detection: true
    }
  });
  
  console.log('Domain:', profile.data.profile.domain.label);
  console.log('Complexity:', profile.data.profile.scores.complexity_level);
  console.log('Language:', profile.data.profile.language.detected_language);
}

testAPI().catch(console.error);
```

---

## Error Testing

### Test Validation Error (Empty Text)
```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": ""}'
```
**Expected**: 422 Unprocessable Entity

### Test Validation Error (Single Word)
```bash
curl -X POST http://localhost:8888/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello"}'
```
**Expected**: 400 Bad Request - "Text must contain at least 2 words"

### Test Batch Size Limit
```bash
# Create a batch with 101 texts (exceeds max of 100)
curl -X POST http://localhost:8888/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d "{\"texts\": $(python3 -c 'print([\"text\"] * 101)')}"
```
**Expected**: 400 Bad Request - "Batch size exceeds maximum"

---

## Monitoring

### Check Container Status
```bash
docker ps | grep request-profiler
```

### View Logs
```bash
docker logs request-profiler
docker logs request-profiler --follow  # Follow logs in real-time
docker logs request-profiler --tail 50  # Last 50 lines
```

### Check Metrics
```bash
curl http://localhost:8888/metrics | grep profiler
```

---

## Rate Limiting

- **Default**: 100 requests per minute per IP address
- Rate limit headers are included in responses:
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Remaining`: Remaining requests
  - `X-RateLimit-Reset`: Reset time

---

## Container Management

### Start Service
```bash
cd /home/aleenajayan/Documents/COSS/SmartModelRouting-main/RequestProfiler
docker compose up -d
```

### Stop Service
```bash
docker compose down
```

### Restart Service
```bash
docker compose restart
```

### Rebuild and Start
```bash
docker compose up -d --build
```

---

## Troubleshooting

### Service Not Responding
1. Check if container is running: `docker ps | grep request-profiler`
2. Check logs: `docker logs request-profiler`
3. Check if port is available: `netstat -tuln | grep 8888`

### Models Not Loading
1. Verify models directory exists: `ls -la models/`
2. Check container logs for model loading errors
3. Ensure models are mounted correctly in docker-compose.yml

### Port Already in Use
If port 8888 is in use, modify `docker-compose.yml`:
```yaml
ports:
  - "9000:8000"  # Change 9000 to any available port
```

---

## Next Steps

1. **Open Interactive Docs**: Visit `http://localhost:8888/docs` in your browser
2. **Test with Real Data**: Use your own text samples
3. **Integrate**: Use the Python/JavaScript examples to integrate into your application
4. **Monitor**: Check `/metrics` endpoint for performance metrics

---

**Happy Testing! 🚀**
