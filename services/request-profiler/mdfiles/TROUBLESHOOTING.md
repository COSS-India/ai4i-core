# Troubleshooting Guide

## Common Issues and Solutions

### 1. Service Not Starting

**Symptom**: Docker container exits immediately or service won't start

**Solutions**:
```bash
# Check Docker logs
docker compose logs profiler

# Verify models exist
ls -lh models/

# Rebuild the image
docker compose down
docker compose build --no-cache
docker compose up -d
```

### 2. Models Not Loading

**Symptom**: `503 Service Unavailable` or "Models not loaded" error

**Solutions**:
```bash
# Verify all model files exist
ls -lh models/
# Expected files:
# - domain_pipeline.pkl
# - complexity_regressor.pkl
# - lid.176.ftz

# Check service health
curl http://localhost:8000/api/v1/health

# View detailed logs
docker compose logs profiler | grep -i model
```

### 3. Port Already in Use

**Symptom**: `Address already in use` error on port 8000

**Solutions**:
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port in docker-compose.yml
# Change: ports: - "8001:8000"
```

### 4. Validation Errors (422)

**Symptom**: API returns 422 Unprocessable Entity

**Causes**:
- Text is empty or whitespace-only
- Text has fewer than 2 words
- Invalid JSON format

**Solutions**:
```bash
# Valid request
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world this is a test"}'

# Invalid (single word)
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello"}'  # Will return 422
```

### 5. Slow Response Times

**Symptom**: Response times exceed 500ms

**Possible Causes**:
- Large batch sizes (>50 texts)
- System resource constraints
- Network latency

**Solutions**:
```bash
# Reduce batch size
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["text1", "text2"]}'  # Use smaller batches

# Check system resources
top  # or htop

# Monitor metrics
curl http://localhost:8000/metrics
```

### 6. Connection Refused

**Symptom**: `Connection refused` when calling API

**Solutions**:
```bash
# Verify container is running
docker compose ps

# Start the service
docker compose up -d

# Wait for service to be ready (30 seconds)
sleep 30
curl http://localhost:8000/api/v1/health
```

### 7. Import or Dependency Errors

**Symptom**: `ModuleNotFoundError` or `ImportError`

**Solutions**:
```bash
# Rebuild Docker image
docker compose down
docker compose build --no-cache
docker compose up -d

# For local development
pip install -r requirements.txt
python3 -m pip install --upgrade pip
```

## Debugging Tips

### Enable Debug Logging
```bash
# Set environment variable in docker-compose.yml
environment:
  - LOG_LEVEL=DEBUG

# Then restart
docker compose restart profiler
docker compose logs -f profiler
```

### Test Models Directly
```python
from request_profiler.profiler import RequestProfiler

profiler = RequestProfiler()
result = profiler.profile("Hello world this is a test")
print(result)
```

### Check Prometheus Metrics
```bash
curl http://localhost:8000/metrics | grep profiler
```

### Verify API Endpoints
```bash
# Health check
curl http://localhost:8000/api/v1/health

# Single profile
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'

# Batch profile
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["text1", "text2"]}'
```

## Getting Help

1. Check the logs: `docker compose logs profiler`
2. Review [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed setup
3. See [API_EXAMPLES.md](API_EXAMPLES.md) for API usage examples
4. Check [PRODUCTION_READY_REPORT.md](PRODUCTION_READY_REPORT.md) for verification details

