# Observability Integration Guide for AI4I Microservices

**Complete guide for integrating Prometheus and Grafana monitoring across all AI4I microservices**

---

## 📋 Table of Contents

- [Overview](#overview)
- [Current Status](#current-status)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Integration Steps](#integration-steps)
- [Configuration Reference](#configuration-reference)
- [Available Metrics](#available-metrics)
- [Testing & Verification](#testing--verification)
- [Dashboards](#dashboards)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## Overview

### What is Observability?

The AI4I observability stack provides comprehensive monitoring and metrics collection for all microservices using:

- **Prometheus** - Time-series metrics collection and storage
- **Grafana** - Visualization and dashboarding
- **Common Observability Module** - Shared Python plugin for FastAPI services

### Key Features

✅ **Request Tracking** - Track all API requests with method, endpoint, status code  
✅ **Performance Metrics** - Monitor request duration, latency, throughput  
✅ **Business Metrics** - Service-specific metrics (NMT characters, TTS characters, ASR audio length)  
✅ **System Monitoring** - CPU, memory, disk usage  
✅ **SLA Tracking** - Availability, response time targets, compliance  
✅ **Health Checks** - Service health and readiness endpoints  

---

## Current Status

### ✅ Completed - NMT Service

The **NMT (Neural Machine Translation) Service** is fully integrated with observability:

| Component | Status | Details |
|-----------|--------|---------|
| **Observability Plugin** | ✅ Integrated | Module copied and initialized |
| **Prometheus Scraping** | ✅ Configured | Scraping every 5 seconds |
| **Grafana Dashboards** | ✅ Available | Real-time NMT monitoring |
| **Metrics Endpoint** | ✅ Active | `http://localhost:8091/enterprise/metrics` |
| **Health Endpoint** | ✅ Active | `http://localhost:8091/enterprise/health` |

**NMT Service Metrics:**
```
✅ telemetry_obsv_requests_total - Total requests by endpoint
✅ telemetry_obsv_request_duration_seconds - Request latency
✅ telemetry_obsv_nmt_characters_translated - Characters translated
✅ telemetry_obsv_system_cpu_percent - CPU usage
✅ telemetry_obsv_system_memory_percent - Memory usage
```

### 📋 Pending Integration

Services ready for observability integration:

- [ ] **ASR Service** (asr-service) - Audio processing metrics
- [ ] **TTS Service** (tts-service) - Text-to-speech metrics
- [ ] **LLM Service** (llm-service) - Token usage metrics
- [ ] **Pipeline Service** (pipeline-service) - Orchestration metrics
- [ ] **API Gateway** (api-gateway-service) - Gateway traffic metrics
- [ ] **Auth Service** (auth-service) - Authentication metrics
- [ ] **Config Service** (config-service) - Configuration access metrics

**Estimated time per service: 10-15 minutes**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI4I Microservices Platform                 │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │   NMT    │  │   TTS    │  │   ASR    │  │   LLM    │      │
│  │ Service  │  │ Service  │  │ Service  │  │ Service  │      │
│  │  :8089   │  │  :8xxx   │  │  :8xxx   │  │  :8xxx   │      │
│  │          │  │          │  │          │  │          │      │
│  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │      │
│  │ │Observ│ │  │ │Observ│ │  │ │Observ│ │  │ │Observ│ │      │
│  │ │Plugin│✅│  │ │Plugin│ │  │ │Plugin│ │  │ │Plugin│ │      │
│  │ └──┬───┘ │  │ └──┬───┘ │  │ └──┬───┘ │  │ └──┬───┘ │      │
│  └────┼─────┘  └────┼─────┘  └────┼─────┘  └────┼─────┘      │
│       │             │              │              │            │
└───────┼─────────────┼──────────────┼──────────────┼────────────┘
        │             │              │              │
        └─────────────┴──────────────┴──────────────┘
                      │
              /enterprise/metrics (every 5s)
                      │
                      ▼
               ┌─────────────┐
               │ Prometheus  │
               │   :9090     │
               │             │
               │ • Scraping  │
               │ • Storage   │
               │ • Queries   │
               └──────┬──────┘
                      │
                      ▼
               ┌─────────────┐
               │  Grafana    │
               │   :3001     │
               │             │
               │ • Dashboards│
               │ • Alerts    │
               │ • Explore   │
               └─────────────┘
```

### Service Ports

| Service | Port | Description |
|---------|------|-------------|
| **Frontend (simple-ui)** | 3000 | React frontend application |
| **Grafana** | **3001** | Monitoring dashboards & visualization |
| **NMT Service** | 8091 (external) / 8089 (internal) | Translation service |
| **Prometheus** | 9090 | Metrics collection & storage |

⚠️ **Note**: Grafana uses port **3001** to avoid conflict with the frontend on port 3000.

---

## Quick Start

### 1. Access Monitoring Stack

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://localhost:3001 | admin / admin |
| **Prometheus** | http://localhost:9090 | - |
| **NMT Metrics** | http://localhost:8091/enterprise/metrics | - |
| **NMT Health** | http://localhost:8091/enterprise/health | - |

### 2. Verify NMT Service Integration

```bash
# Check if metrics are being collected
curl http://localhost:8091/enterprise/metrics

# Check service health
curl http://localhost:8091/enterprise/health

# Expected health response:
# {
#   "status": "healthy",
#   "plugin": "dhruva-enterprise",
#   "version": "1.0.3",
#   "enabled": true
# }
```

### 3. View Metrics in Prometheus

```bash
# Open Prometheus UI
open http://localhost:9090

# Check if NMT service target is UP
# Navigate to: Status > Targets > nmt-service-observability

# Query some metrics in Graph tab:
telemetry_obsv_requests_total{job="nmt-service-observability"}
rate(telemetry_obsv_request_duration_seconds_sum[5m])
```

### 4. View Dashboards in Grafana

```bash
# Open Grafana
open http://localhost:3001

# Login: admin / admin

# Navigate to:
# Dashboards > NMT Service - Real-time Monitoring
```

---

## Integration Steps

Follow these steps to integrate observability into any microservice.

### Prerequisites

- ✅ Common observability module at `common/observability/`
- ✅ Prometheus and Grafana services running
- ✅ Docker Compose configured
- ✅ Service uses FastAPI framework

### Step 1: Update Dockerfile

**IMPORTANT**: The build context must be the project root (`.`) in `docker-compose.yml`.

#### 1.1 Update docker-compose.yml build context

```yaml
your-service:
  build:
    context: .  # ← Project root, not ./services/your-service
    dockerfile: ./services/your-service/Dockerfile
  # ... rest of config
```

#### 1.2 Update Dockerfile

Add the observability module copy **BEFORE** copying application code:

```dockerfile
# Stage 2: Final Runtime
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash app

# Copy python packages from builder
COPY --from=builder /root/.local /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# ⭐ CRITICAL: Copy common observability module
COPY --chown=app:app common/observability /app/observability

# Copy application code (now relative to project root)
COPY --chown=app:app services/your-service/. .

RUN chown -R app:app /app /home/app/.local

USER app

EXPOSE 8089

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8089/health || exit 1

ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8089"]
```

#### 1.3 Update Builder Stage (if using multi-stage)

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ curl libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service directory
COPY services/your-service/requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt
```

### Step 2: Update requirements.txt

Add observability dependencies to your service's `requirements.txt`:

```txt
# Observability and metrics
prometheus-client>=0.19.0
psutil>=5.9.0
pyjwt>=2.8.0
```

### Step 3: Integrate Plugin in main.py

#### 3.1 Add Imports (at the top of main.py)

```python
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# ⭐ Dhruva Observability Plugin Integration (Local Module)
try:
    from observability import ObservabilityPlugin
    OBSERVABILITY_AVAILABLE = True
    logger.info("✅ Using local observability module")
except ImportError as e:
    OBSERVABILITY_AVAILABLE = False
    logger.warning(f"⚠️  Local observability module not available: {e}")
```

#### 3.2 Initialize Plugin (after creating FastAPI app)

```python
# Create FastAPI app
app = FastAPI(
    title="Your Service Name",
    version="1.0.0",
    description="Your service description"
)

# ⭐ Initialize Dhruva Observability Plugin
if OBSERVABILITY_AVAILABLE:
    try:
        observability_plugin = ObservabilityPlugin()
        observability_plugin.register_plugin(app)
        logger.info("✅ Dhruva Observability Plugin initialized successfully for Your Service")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Dhruva Observability Plugin: {e}")
        OBSERVABILITY_AVAILABLE = False
else:
    logger.info("ℹ️  Dhruva Observability Plugin not available for Your Service")
```

### Step 4: Update docker-compose.yml

Add observability environment variables directly to the service definition:

```yaml
your-service:
  build:
    context: .
    dockerfile: ./services/your-service/Dockerfile
  container_name: ai4v-your-service
  ports:
    - "8091:8089"
  environment:
    # Observability Configuration
    - OBSERVE_UTIL_ENABLED=true
    - OBSERVE_UTIL_DEBUG=true
    - OBSERVE_UTIL_METRICS_PATH=/enterprise/metrics
    - OBSERVE_UTIL_HEALTH_PATH=/enterprise/health
    - OBSERVE_UTIL_COLLECT_SYSTEM_METRICS=true
    - OBSERVE_UTIL_COLLECT_GPU_METRICS=false
    - OBSERVE_UTIL_COLLECT_DB_METRICS=true
  env_file:
    - ./services/your-service/.env
  depends_on:
    config-service:
      condition: service_healthy
  networks:
    - microservices-network
```

### Step 5: Update Service env.template

Add observability configuration to your service's `env.template`:

```bash
# Observability Configuration
OBSERVE_UTIL_ENABLED=true
OBSERVE_UTIL_DEBUG=false
OBSERVE_UTIL_METRICS_PATH=/enterprise/metrics
OBSERVE_UTIL_HEALTH_PATH=/enterprise/health
OBSERVE_UTIL_COLLECT_SYSTEM_METRICS=true
OBSERVE_UTIL_COLLECT_GPU_METRICS=false
OBSERVE_UTIL_COLLECT_DB_METRICS=true
OBSERVE_UTIL_AVAILABILITY_TARGET=99.9
OBSERVE_UTIL_RESPONSE_TIME_TARGET=1.0
OBSERVE_UTIL_THROUGHPUT_TARGET=20.0
OBSERVE_UTIL_CUSTOMERS=
OBSERVE_UTIL_APPS=
```

### Step 6: Update Prometheus Configuration

Add your service to Prometheus scrape targets in `infrastructure/prometheus/prometheus.yml`:

```yaml
scrape_configs:
  # ... existing jobs

  # Your Service Observability Metrics
  - job_name: "your-service-observability"
    scrape_interval: 5s
    static_configs:
      - targets: ["your-service:8089"]
    metrics_path: "/enterprise/metrics"
```

### Step 7: Build and Deploy

```bash
# Rebuild the service
docker compose build your-service

# Start the service
docker compose up -d your-service

# Check logs
docker logs ai4v-your-service

# Look for:
# ✅ Using local observability module
# ✅ Dhruva Observability Plugin initialized successfully
```

### Step 8: Verify Integration

```bash
# 1. Check metrics endpoint
curl http://localhost:PORT/enterprise/metrics

# 2. Check health endpoint
curl http://localhost:PORT/enterprise/health

# 3. Verify Prometheus target
open http://localhost:9090/targets
# Look for "your-service-observability" - should be UP

# 4. Query metrics in Prometheus
# Navigate to Graph tab and query:
telemetry_obsv_requests_total{job="your-service-observability"}
```

---

## Configuration Reference

### Environment Variables

All observability configuration uses the `OBSERVE_UTIL_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `OBSERVE_UTIL_ENABLED` | `false` | Enable/disable observability plugin |
| `OBSERVE_UTIL_DEBUG` | `false` | Enable debug logging |
| `OBSERVE_UTIL_METRICS_PATH` | `/enterprise/metrics` | Prometheus metrics endpoint |
| `OBSERVE_UTIL_HEALTH_PATH` | `/enterprise/health` | Health check endpoint |
| `OBSERVE_UTIL_COLLECT_SYSTEM_METRICS` | `true` | Collect CPU/memory metrics |
| `OBSERVE_UTIL_COLLECT_GPU_METRICS` | `false` | Collect GPU metrics (if available) |
| `OBSERVE_UTIL_COLLECT_DB_METRICS` | `true` | Collect database metrics |
| `OBSERVE_UTIL_AVAILABILITY_TARGET` | `99.9` | SLA availability target (%) |
| `OBSERVE_UTIL_RESPONSE_TIME_TARGET` | `1.0` | Response time target (seconds) |
| `OBSERVE_UTIL_THROUGHPUT_TARGET` | `20.0` | Throughput target (req/sec) |
| `OBSERVE_UTIL_CUSTOMERS` | `""` | Comma-separated customer list |
| `OBSERVE_UTIL_APPS` | `""` | Comma-separated app list |

### Grafana Configuration

```bash
# In root .env or env.template
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

---

## Available Metrics

### Request Metrics

Track all HTTP requests with labels:

```prometheus
telemetry_obsv_requests_total{organization, app, method, endpoint, status_code}
telemetry_obsv_request_duration_seconds{organization, app, method, endpoint}
telemetry_obsv_request_duration_seconds_bucket{organization, app, method, endpoint, le}
telemetry_obsv_request_duration_seconds_sum{organization, app, method, endpoint}
telemetry_obsv_request_duration_seconds_count{organization, app, method, endpoint}
```

**Example Queries:**
```prometheus
# Total requests
telemetry_obsv_requests_total

# Request rate (requests per second)
rate(telemetry_obsv_requests_total[5m])

# Average request duration
rate(telemetry_obsv_request_duration_seconds_sum[5m])
/
rate(telemetry_obsv_request_duration_seconds_count[5m])

# 95th percentile latency
histogram_quantile(0.95, 
  rate(telemetry_obsv_request_duration_seconds_bucket[5m])
)
```

### Service-Specific Metrics

#### NMT Service
```prometheus
telemetry_obsv_nmt_characters_translated{organization, app, source_language, target_language}
telemetry_obsv_data_processed_total{organization, app, data_type="nmt_characters"}
```

#### TTS Service
```prometheus
telemetry_obsv_tts_characters_synthesized{organization, app, language}
telemetry_obsv_tts_audio_seconds_generated{organization, app, language}
```

#### ASR Service
```prometheus
telemetry_obsv_asr_audio_seconds_processed{organization, app, language}
telemetry_obsv_asr_words_transcribed{organization, app, language}
```

#### LLM Service
```prometheus
telemetry_obsv_llm_tokens_processed_total{organization, app, model}
telemetry_obsv_llm_input_tokens{organization, app, model}
telemetry_obsv_llm_output_tokens{organization, app, model}
```

### System Metrics

Monitor system resources:

```prometheus
telemetry_obsv_system_cpu_percent
telemetry_obsv_system_memory_percent
telemetry_obsv_system_disk_usage_percent
telemetry_obsv_system_network_bytes_sent
telemetry_obsv_system_network_bytes_received
```

### Database Metrics

```prometheus
telemetry_obsv_db_connections_active
telemetry_obsv_db_connections_idle
telemetry_obsv_db_query_duration_seconds
```

### Error Metrics

```prometheus
telemetry_obsv_errors_total{organization, app, endpoint, status_code, error_type}
```

### SLA Metrics

```prometheus
telemetry_obsv_sla_availability_percent{organization, app}
telemetry_obsv_sla_response_time_seconds{organization, app}
telemetry_obsv_sla_compliance_percent{organization, app, sla_type}
```

---

## Testing & Verification

### Complete Verification Checklist

#### 1. Service Health Check

```bash
# Check service is running
docker ps | grep your-service

# Check service logs
docker logs ai4v-your-service

# Look for success messages:
# ✅ Using local observability module
# ✅ Dhruva Observability Plugin initialized successfully
```

#### 2. Metrics Endpoint

```bash
# Access metrics endpoint
curl http://localhost:PORT/enterprise/metrics

# Should return Prometheus-formatted metrics like:
# HELP telemetry_obsv_requests_total Total enterprise requests
# TYPE telemetry_obsv_requests_total counter
# telemetry_obsv_requests_total{...} 123.0
```

#### 3. Health Endpoint

```bash
# Access health endpoint
curl http://localhost:PORT/enterprise/health

# Expected response:
{
  "status": "healthy",
  "plugin": "dhruva-enterprise",
  "version": "1.0.3",
  "enabled": true
}
```

#### 4. Prometheus Targets

```bash
# Open Prometheus UI
open http://localhost:9090/targets

# Verify your service target:
# - State: UP
# - Labels: job="your-service-observability"
# - Last Scrape: < 5s ago
# - Scrape Duration: < 1s
```

#### 5. Query Metrics in Prometheus

```bash
# Open Prometheus Graph
open http://localhost:9090/graph

# Test queries:
telemetry_obsv_requests_total{job="your-service-observability"}
rate(telemetry_obsv_requests_total[5m])
up{job="your-service-observability"}
```

#### 6. Generate Test Traffic

```bash
# Make some requests to generate metrics
for i in {1..10}; do
  curl http://localhost:PORT/your-endpoint
  sleep 1
done

# Check if request count increased
curl http://localhost:PORT/enterprise/metrics | grep requests_total
```

#### 7. View in Grafana

```bash
# Open Grafana
open http://localhost:3001

# Login: admin / admin

# Steps:
# 1. Go to Explore
# 2. Select "Prometheus" datasource
# 3. Enter query: telemetry_obsv_requests_total{job="your-service-observability"}
# 4. Click "Run query"
# 5. You should see metrics data!
```

### Integration Success Criteria

Your integration is successful when:

- ✅ Service starts without errors
- ✅ `/enterprise/metrics` returns Prometheus metrics
- ✅ `/enterprise/health` returns healthy status
- ✅ Prometheus target shows as **UP**
- ✅ Metrics appear in Prometheus queries
- ✅ Grafana can query and display metrics
- ✅ Metrics update in real-time as requests are made

---

## Dashboards

### Available Dashboards

#### 1. NMT Service - Real-time Monitoring
**URL**: http://localhost:3001/d/nmt-service-dashboard

**Panels:**
- Total Translation Requests
- Request Rate (req/sec)
- Average Request Duration
- Request Duration Trend
- All NMT Endpoints Activity
- Response Status Codes
- Requests by Organization

**Best for**: NMT service-specific monitoring

#### 2. Dhruva DevOps Operations Dashboard (v3 & v4)
**URL**: http://localhost:3001/dashboards

**Note**: These dashboards are designed for services with the following endpoints:
- `/services/inference/translation`
- `/services/inference/asr`
- `/services/inference/tts`

If your service uses different endpoints (like NMT's `/api/v1/nmt/inference`), you'll need to:
1. Use the NMT-specific dashboard, OR
2. Create a custom dashboard with your endpoint patterns

### Creating Custom Dashboards

1. Open Grafana: http://localhost:3001
2. Go to **Dashboards** > **New Dashboard**
3. Click **Add visualization**
4. Select **Prometheus** datasource
5. Enter your query (e.g., `telemetry_obsv_requests_total{job="your-service"}`)
6. Customize visualization type (Graph, Stat, Gauge, etc.)
7. Save dashboard

**Useful Query Examples:**

```prometheus
# Request rate
rate(telemetry_obsv_requests_total{job="your-service-observability"}[5m])

# Average latency
rate(telemetry_obsv_request_duration_seconds_sum[5m])
/
rate(telemetry_obsv_request_duration_seconds_count[5m])

# Error rate
rate(telemetry_obsv_errors_total[5m])

# Success rate percentage
sum(rate(telemetry_obsv_requests_total{status_code=~"2.."}[5m]))
/
sum(rate(telemetry_obsv_requests_total[5m]))
* 100
```

---

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'observability'

**Symptoms:**
```
ImportError: cannot import name 'ObservabilityPlugin' from 'observability'
```

**Solutions:**

1. **Check Dockerfile COPY command**
   ```dockerfile
   # Correct (with project root as build context)
   COPY --chown=app:app common/observability /app/observability
   
   # Incorrect (with service dir as build context)
   COPY --chown=app:app ../../common/observability /app/observability
   ```

2. **Verify build context in docker-compose.yml**
   ```yaml
   your-service:
     build:
       context: .  # Must be project root
       dockerfile: ./services/your-service/Dockerfile
   ```

3. **Rebuild the service**
   ```bash
   docker compose build your-service
   docker compose up -d your-service
   ```

4. **Verify module was copied**
   ```bash
   docker exec -it ai4v-your-service ls -la /app/observability
   ```

### Issue: Metrics endpoint returns 404

**Symptoms:**
```bash
curl http://localhost:PORT/enterprise/metrics
# Returns: 404 Not Found
```

**Solutions:**

1. **Check if plugin is enabled**
   ```bash
   # In docker-compose.yml or .env
   OBSERVE_UTIL_ENABLED=true
   ```

2. **Verify plugin initialized**
   ```bash
   docker logs ai4v-your-service | grep -i observability
   # Should see: ✅ Dhruva Observability Plugin initialized successfully
   ```

3. **Check for initialization errors**
   ```bash
   docker logs ai4v-your-service | grep -i error
   ```

4. **Restart service**
   ```bash
   docker compose restart your-service
   ```

### Issue: Prometheus not scraping metrics (Target DOWN)

**Symptoms:**
- Prometheus shows target as **DOWN**
- Error: "Get http://your-service:8089/enterprise/metrics: context deadline exceeded"

**Solutions:**

1. **Check service is running**
   ```bash
   docker ps | grep your-service
   ```

2. **Verify service health**
   ```bash
   curl http://localhost:PORT/health
   ```

3. **Check network connectivity**
   ```bash
   # From Prometheus container
   docker exec -it ai4v-prometheus ping your-service
   docker exec -it ai4v-prometheus wget -O- http://your-service:8089/enterprise/metrics
   ```

4. **Verify Prometheus config**
   ```bash
   docker exec -it ai4v-prometheus cat /etc/prometheus/prometheus.yml
   # Check if your service job exists
   ```

5. **Reload Prometheus config**
   ```bash
   docker compose restart prometheus
   ```

### Issue: No data in Grafana dashboards

**Symptoms:**
- Dashboard shows "No data"
- Queries return empty results

**Solutions:**

1. **Verify Prometheus is scraping**
   ```bash
   open http://localhost:9090/targets
   # All targets should be UP
   ```

2. **Check if metrics exist in Prometheus**
   ```bash
   open http://localhost:9090/graph
   # Query: telemetry_obsv_requests_total
   # Should return data
   ```

3. **Verify Grafana datasource**
   - Go to Grafana > Configuration > Data Sources
   - Select "Prometheus"
   - URL should be: `http://prometheus:9090`
   - Click "Save & test" - should show ✅ Data source is working

4. **Check dashboard queries**
   - Open dashboard in edit mode
   - Check if endpoint filters match your actual endpoints
   - Example: If your endpoint is `/api/v1/nmt/inference`, use:
     ```prometheus
     telemetry_obsv_requests_total{endpoint="/api/v1/nmt/inference"}
     ```

5. **Generate test traffic**
   ```bash
   # Make requests to generate metrics
   for i in {1..20}; do curl http://localhost:PORT/your-endpoint; done
   ```

### Issue: Observability plugin disabled in logs

**Symptoms:**
```
⚠️ Dhruva Observability plugin is disabled
```

**Solutions:**

1. **Add environment variables to docker-compose.yml**
   ```yaml
   your-service:
     environment:
       - OBSERVE_UTIL_ENABLED=true
       - OBSERVE_UTIL_DEBUG=true
     env_file:
       - ./services/your-service/.env
   ```

2. **Verify .env file**
   ```bash
   cat services/your-service/.env | grep OBSERVE_UTIL_ENABLED
   # Should show: OBSERVE_UTIL_ENABLED=true
   ```

3. **Recreate container**
   ```bash
   docker compose stop your-service
   docker compose rm -f your-service
   docker compose up -d your-service
   ```

### Issue: Dashboard panels show wrong data

**Symptoms:**
- Panels show data from different service
- Metrics don't match your service

**Solution:**

The existing "Dhruva DevOps Operations Dashboard" uses specific endpoint patterns:
- `/services/inference/translation`
- `/services/inference/asr`
- `/services/inference/tts`

If your service uses different endpoints, create a custom dashboard or modify queries to match your endpoints.

---

## Next Steps

### For Services Already Integrated (NMT)

1. **Create custom dashboards** for service-specific metrics
2. **Set up alerts** for high error rates, latency spikes
3. **Monitor regularly** and tune SLA targets
4. **Export dashboards** for version control

### For Services Pending Integration

Use this checklist for each service:

- [ ] Update `docker-compose.yml` build context to project root
- [ ] Update Dockerfile to copy `common/observability`
- [ ] Update all COPY paths in Dockerfile to be relative to project root
- [ ] Add dependencies to `requirements.txt`
- [ ] Import and initialize `ObservabilityPlugin` in `main.py`
- [ ] Add observability env vars to `docker-compose.yml`
- [ ] Add observability config to service `.env` / `env.template`
- [ ] Add service to Prometheus scrape config
- [ ] Rebuild service: `docker compose build service-name`
- [ ] Start service: `docker compose up -d service-name`
- [ ] Verify metrics: `curl http://localhost:PORT/enterprise/metrics`
- [ ] Check Prometheus targets: http://localhost:9090/targets
- [ ] View in Grafana: http://localhost:3001

### Priority Order for Integration

1. **ASR Service** - High traffic, critical for audio processing
2. **TTS Service** - High traffic, critical for audio generation
3. **LLM Service** - High cost, need token usage monitoring
4. **Pipeline Service** - Orchestration visibility
5. **API Gateway** - Overall traffic patterns
6. **Auth Service** - Security monitoring
7. **Config Service** - Configuration access tracking

---

## Additional Resources

### Documentation
- **Common Observability Module**: `/common/observability/`
- **Prometheus Documentation**: https://prometheus.io/docs/
- **Grafana Documentation**: https://grafana.com/docs/
- **Prometheus Client Python**: https://github.com/prometheus/client_python

### Useful Commands

```bash
# View all service logs
docker compose logs -f

# View specific service logs
docker logs -f ai4v-your-service

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq

# Check Grafana datasources
curl -u admin:admin http://localhost:3001/api/datasources | jq

# Test metrics endpoint
watch -n 1 'curl -s http://localhost:PORT/enterprise/metrics | grep requests_total'

# Monitor Prometheus scrape
watch -n 1 'curl -s http://localhost:9090/api/v1/targets | jq ".data.activeTargets[] | select(.job==\"your-service-observability\") | .health"'
```

### Quick Reference - Files Modified Per Service

```
services/your-service/
├── Dockerfile ...................... Add observability COPY
├── requirements.txt ................ Add prometheus-client, psutil, pyjwt
├── main.py ......................... Import & initialize ObservabilityPlugin
└── env.template .................... Add OBSERVE_UTIL_* variables

infrastructure/prometheus/
└── prometheus.yml .................. Add scrape job

docker-compose.yml .................. Update build context & add env vars
```

---

## Summary

### ✅ What We Have

- **Monitoring Stack**: Prometheus (9090) + Grafana (3001)
- **NMT Service**: Fully integrated with observability
- **Metrics Collection**: Every 5 seconds from NMT service
- **Dashboards**: Real-time NMT monitoring dashboard
- **Documentation**: Complete integration guide (this file)

### 📋 What's Next

- Integrate remaining microservices (ASR, TTS, LLM, Pipeline, etc.)
- Create service-specific dashboards
- Set up alerting rules
- Configure notification channels (Slack, email, etc.)
- Export dashboards to version control

### 🎯 Integration Time

- **Average time per service**: 10-15 minutes
- **7 remaining services**: ~2 hours total
- **Already completed**: NMT Service ✅

---

**Last Updated**: November 25, 2025  
**Version**: 2.0.0  
**Status**: ✅ NMT Service Complete | 📋 6+ Services Pending  
**Maintained by**: AI4I Platform Team
