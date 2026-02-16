# RequestProfiler - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Clone and Navigate

```bash
git clone <repository-url>
cd RequestProfiler
```

### Step 2: Start with Docker (Recommended)

```bash
# Build and start
docker compose up -d

# Check logs
docker compose logs -f profiler
```

### Step 3: Verify

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Run automated tests
python scripts/test_docker_deployment.py
```

### Step 4: Test the API

```bash
# Profile a medical text
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The patient presents with acute myocardial infarction requiring immediate intervention."
  }'

# Profile Hindi text
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{
    "text": "रोगी को तीव्र हृदयाघात हुआ है और तत्काल उपचार की आवश्यकता है।"
  }'

# Batch profiling
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Medical diagnosis and treatment plan.",
      "यह एक सामान्य वाक्य है।",
      "The contract is hereby terminated."
    ]
  }'
```

### Step 5: Explore

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Metrics**: http://localhost:8000/metrics

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Main documentation |
| [API_DOCUMENTATION.md](API_DOCUMENTATION.md) | Detailed API reference |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | Production deployment |
| [MIGRATION_NOTES.md](MIGRATION_NOTES.md) | Refactoring changelog |
| [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) | Refactoring overview |

---

## 🛠️ Common Commands

### Docker

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Rebuild
docker compose build

# View logs
docker compose logs -f profiler

# Restart
docker compose restart profiler
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn request_profiler.main:app --reload

# Run tests
pytest tests/

# Install dev dependencies
pip install -r requirements-dev.txt
```

### Testing

```bash
# Automated deployment tests
python scripts/test_docker_deployment.py

# Integration tests
python scripts/test_integration.py

# Unit tests
pytest tests/
```

---

## 🎯 Supported Features

- ✅ **6 Indian Languages**: Hindi, Bengali, Tamil, Telugu, Kannada, Assamese
- ✅ **6 Domains**: Medical, Legal, Technical, Finance, Casual, General
- ✅ **Complexity Scoring**: Multi-dimensional analysis (0.0-1.0)
- ✅ **Language Detection**: Automatic language identification
- ✅ **Entity Extraction**: Named entity recognition
- ✅ **Batch Processing**: Process multiple texts efficiently
- ✅ **Prometheus Metrics**: Ready for monitoring integration

---

## 🔧 Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs profiler

# Common fixes:
# 1. Port 8000 in use - change port in docker-compose.yml
# 2. Models missing - ensure models/ directory exists
# 3. Insufficient memory - increase limit in docker-compose.yml
```

### Slow responses

```bash
# Check resource usage
docker stats request-profiler

# Increase resources in docker-compose.yml:
# memory: 2G
# cpus: "4.0"
```

### Models not loading

```bash
# Verify models exist
ls -lh models/

# Download fastText model if missing
cd models/
wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
```

---

## 📊 Performance Targets

- **Latency**: <500ms (P95)
- **Throughput**: 100+ requests/minute
- **Memory**: <1GB under normal load
- **CPU**: <2 cores under normal load

---

## 🎉 You're Ready!

The RequestProfiler is now running and ready to profile translation requests.

For detailed information, see:
- **API Usage**: [API_DOCUMENTATION.md](API_DOCUMENTATION.md)
- **Deployment**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **Full Documentation**: [README.md](README.md)

