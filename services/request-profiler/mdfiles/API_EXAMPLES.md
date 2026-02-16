# RequestProfiler API Examples

## Health Check

```bash
curl -X GET http://localhost:8000/api/v1/health
```

**Response**:
```json
{
  "status": "healthy",
  "models_loaded": true,
  "timestamp": "2026-02-12T06:46:27.169555Z"
}
```

---

## Single Text Profiling

### Example 1: Simple Text (LOW Complexity)

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world this is a test"}'
```

**Response**:
```json
{
  "profile": {
    "text": "Hello world this is a test",
    "language": "en",
    "domain": "General",
    "scores": {
      "complexity_score": 0.2319,
      "complexity_level": "LOW",
      "feature_contributions": {
        "terminology_density": 0.08,
        "entity_density": 0.05,
        "avg_sentence_len": 0.04
      }
    }
  }
}
```

### Example 2: Medical Text with Multiple Spaces

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient has fever.   Temperature: 102°F.   Prescription: Paracetamol."}'
```

**Response**: ✓ ACCEPTED (multiple spaces handled correctly)

### Example 3: Text with Newlines

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Line one.\n\nLine two.\n\nLine three."}'
```

**Response**: ✓ ACCEPTED (newlines preserved)

---

## Batch Profiling

```bash
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Hello world this is a test",
      "The quick brown fox jumps over the lazy dog",
      "Medical terminology and complex pharmaceutical interactions"
    ]
  }'
```

**Response**:
```json
{
  "profiles": [
    {
      "text": "Hello world this is a test",
      "language": "en",
      "domain": "General",
      "scores": {
        "complexity_score": 0.2258,
        "complexity_level": "LOW"
      }
    },
    ...
  ]
}
```

---

## Error Handling

### Empty Text (422 Validation Error)

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": ""}'
```

**Response**: 422 Unprocessable Entity

### Single Word (422 Validation Error)

```bash
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello"}'
```

**Response**: 422 Unprocessable Entity

### Batch Size Exceeds 50 (422 Validation Error)

```bash
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["text one two"] * 51}'
```

**Response**: 422 Unprocessable Entity

---

## Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

**Response**: Prometheus metrics in text format

---

## Complexity Level Examples

### LOW Complexity (score < 0.5)
- "Simple text here" → 0.2319
- "The quick brown fox" → 0.27

### HIGH Complexity (score ≥ 0.5)
- Complex medical/legal terminology
- Long sentences with sophisticated vocabulary
- Technical documentation

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Single profiling
response = requests.post(
    f"{BASE_URL}/profile",
    json={"text": "Hello world this is a test"}
)
print(response.json())

# Batch profiling
response = requests.post(
    f"{BASE_URL}/profile/batch",
    json={"texts": ["text one", "text two"]}
)
print(response.json())
```

---

## Status Codes

- **200**: Success
- **422**: Validation error (empty text, single word, oversized text, batch >50)
- **500**: Server error

