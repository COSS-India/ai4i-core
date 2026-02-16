# RequestProfiler Deployment Guide

## Quick Start

### Prerequisites
- Docker 24.0+ (with BuildKit support)
- Docker Compose v2
- 2GB RAM minimum
- 1GB disk space

### 1. Build and Start the Container

```bash
# Build the Docker image
docker compose build

# Start the service
docker compose up -d

# Check logs
docker compose logs -f profiler
```

### 2. Verify Deployment

```bash
# Check health
curl http://localhost:8000/api/v1/health

# Run comprehensive tests
python scripts/test_docker_deployment.py
```

### 3. Test the API

```bash
# Single text profiling
curl -X POST http://localhost:8000/api/v1/profile \
  -H "Content-Type: application/json" \
  -d '{"text": "The patient requires immediate medical attention."}'

# Batch profiling
curl -X POST http://localhost:8000/api/v1/profile/batch \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Medical text here", "Legal text here"]}'

# Check metrics
curl http://localhost:8000/metrics
```

## Production Deployment

### Environment Variables

Create a `.env` file in the project root:

```bash
# Service Configuration
LOG_LEVEL=info
ENVIRONMENT=production
SERVICE_VERSION=1.0.0

# Model Paths
MODEL_DIR=/app/models

# Performance Settings
MAX_TEXT_LENGTH=50000
MAX_BATCH_SIZE=50
REQUEST_TIMEOUT=30

# Rate Limiting
RATE_LIMIT_PER_MINUTE=100

# Monitoring
ENABLE_METRICS=true
```

### Resource Limits

The default `docker-compose.yml` sets:
- **Memory**: 1GB limit, 512MB reservation
- **CPU**: 2.0 cores limit, 1.0 core reservation

Adjust these in `docker-compose.yml` based on your workload:

```yaml
deploy:
  resources:
    limits:
      memory: 2G      # Increase for larger models
      cpus: "4.0"     # Increase for higher throughput
    reservations:
      memory: 1G
      cpus: "2.0"
```

### Health Checks

The container includes automatic health checks:
- **Interval**: 30 seconds
- **Timeout**: 5 seconds
- **Retries**: 3
- **Start Period**: 20 seconds

Monitor health status:
```bash
docker compose ps
docker inspect request-profiler | jq '.[0].State.Health'
```

### Monitoring & Metrics

Metrics are exposed at `http://localhost:8000/metrics` in Prometheus format.

**Key Metrics:**
- `profiler_requests_total` - Total requests by domain/complexity/status
- `profiler_latency_seconds` - Request latency histogram
- `profiler_text_length_words` - Input text length distribution
- `profiler_batch_size` - Batch size distribution
- `profiler_model` - Model version information

**Integration with Existing Prometheus:**

Add this scrape config to your Prometheus `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'request-profiler'
    static_configs:
      - targets: ['profiler:8000']  # Or use host IP
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Logging

View logs:
```bash
# Follow logs
docker compose logs -f profiler

# Last 100 lines
docker compose logs --tail=100 profiler

# Export logs
docker compose logs profiler > profiler.log
```

### Scaling

Run multiple instances:
```bash
docker compose up -d --scale profiler=3
```

Use a load balancer (nginx, HAProxy) to distribute traffic.

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs profiler

# Common issues:
# 1. Models not found - ensure models/ directory exists
# 2. Port 8000 in use - change port in docker-compose.yml
# 3. Insufficient memory - increase memory limit
```

### Slow Response Times

```bash
# Check resource usage
docker stats request-profiler

# Solutions:
# 1. Increase CPU/memory limits
# 2. Use .ftz model instead of .bin (smaller, faster)
# 3. Reduce max_batch_size
# 4. Add more workers in CMD
```

### Model Loading Errors

```bash
# Verify models exist
docker exec request-profiler ls -lh /app/models/

# Re-download models if needed
# (from host)
cd models/
wget https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz
```

## Maintenance

### Update Models

```bash
# Stop container
docker compose down

# Update model files in models/
# ...

# Restart
docker compose up -d
```

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d

# Verify
python scripts/test_docker_deployment.py
```

### Backup

```bash
# Backup models and data
tar -czf backup-$(date +%Y%m%d).tar.gz models/ data/

# Restore
tar -xzf backup-YYYYMMDD.tar.gz
```

## Performance Targets

- **Latency**: <500ms (P95)
- **Throughput**: 100+ requests/minute
- **Memory**: <1GB under normal load
- **CPU**: <2 cores under normal load

Monitor these with the `/metrics` endpoint and adjust resources as needed.

