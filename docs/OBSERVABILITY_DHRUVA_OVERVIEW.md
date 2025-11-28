## AI4I Core Observability & Dhruva Plugin – End‑to‑End Guide

This is the single, up‑to‑date guide for how observability works in AI4I Core:

- **What we use:** Dhruva Observability Plugin (`libs/dhruva_observability`) + Prometheus + Grafana  
- **Where metrics live:** On each service (NMT, TTS, ASR, LLM), not on the API gateway  
- **How it is wired:** Via Docker build (`pip install -e`), Prometheus scrape config, and Grafana dashboards  

Older documents about `ai4i_observability` and low‑level build details are now superseded by this guide.

---

## 1. What You Get From the Dhruva Observability Plugin

- **Automatic request metrics**
  - Counts and latencies for every HTTP request
  - Exposed via `/enterprise/metrics`
- **Automatic business metrics**
  - NMT: characters translated
  - TTS: characters synthesized
  - ASR: audio seconds processed
- **Multi‑tenant context**
  - Extracts `organization` and `app` from JWT/header/API key
- **No manual metric calls**
  - You do not call `record_*` functions in routers; plugin reads the request body and headers

Key metric name pattern: all metrics start with the `telemetry_obsv_` prefix, for example:

- `telemetry_obsv_requests_total`
- `telemetry_obsv_request_duration_seconds`
- `telemetry_obsv_tts_characters_synthesized`
- `telemetry_obsv_nmt_characters_translated`
- `telemetry_obsv_asr_audio_seconds_processed`

---

## 2. High‑Level Architecture

At a high level:

```text
Client/API Gateway (8080) ──► NMT/TTS/ASR/LLM services
                                   │
                                   │ (Dhruva plugin exposes /enterprise/metrics)
                                   ▼
                         Prometheus (9090) ──► Grafana (3001)
```

- Each service runs its **own FastAPI app** and mounts the Dhruva plugin.  
- Each service exposes:
  - `/enterprise/metrics` (plugin metrics, scraped by Prometheus)
  - `/enterprise/health` (plugin health)
  - Regular `/health`, `/docs`, etc. from the service itself.
- **Prometheus scrapes services directly** on their service ports inside Docker (best practice).  
- **Grafana** reads from Prometheus and shows dashboards.

### Ports (host side)

From your host machine (after `docker compose up`):

| Component        | Host Port | Container Port | Example URL                          |
|------------------|-----------|----------------|--------------------------------------|
| API Gateway      | 8080      | 8080           | `http://localhost:8080`             |
| NMT Service      | 8091      | 8089           | `http://localhost:8091/enterprise/metrics` |
| TTS Service      | 8088      | 8088           | `http://localhost:8088/enterprise/metrics` |
| ASR Service      | 8087      | 8087           | `http://localhost:8087/enterprise/metrics` |
| LLM Service      | 8093      | 8090           | `http://localhost:8093/enterprise/metrics` |
| Prometheus       | 9090      | 9090           | `http://localhost:9090`             |
| Grafana          | 3001      | 3000           | `http://localhost:3001`             |

Prometheus runs inside the Docker network and talks to services on container ports like `nmt-service:8089`, `tts-service:8088`, etc.

---

## 3. Build & Packaging Model (How the Plugin Reaches the Service)

The Dhruva plugin is a **pip package** stored in the repo as source:

```text
libs/
  dhruva_observability/
    dhruva_observability/   # package code
    pyproject.toml          # package metadata & deps
    README.md
```

Each service’s Dockerfile:

1. **Copies the plugin source into the build context**
2. **Installs it with `pip install -e` (editable install)**

Example (NMT/TTS Dockerfile pattern):

```dockerfile
# Copy Dhruva plugin source into image
COPY libs/dhruva_observability /app/libs/dhruva_observability

# Install as editable pip package in the builder image
RUN pip install --no-cache-dir --user -e /app/libs/dhruva_observability
```

### What `pip install -e` does (short version)

- Reads `pyproject.toml` and installs required dependencies (FastAPI, Prometheus client, etc.).  
- Creates a small `.egg-link` file in `site-packages` that points to `/app/libs/dhruva_observability`.  
- Python import then works in your code:

```python
from dhruva_observability import ObservabilityPlugin, PluginConfig
```

You do **not** need to set `PYTHONPATH` manually for the plugin; pip handles that.

### Shared‑code vs plugin (why they are different)

- The Dhruva plugin is a **package with its own dependencies**, so using `pip install -e` is appropriate.  
- Other shared code (for example, common auth/DB helpers) can be copied as plain Python modules (like a `common/` folder) and imported via `PYTHONPATH`.  
- Both patterns can coexist; this guide focuses on the plugin side.

---

## 4. Integrating the Dhruva Plugin into a Service

The integration has two main parts:

1. **Dockerfile**: make the plugin available in the container  
2. **`main.py`**: register the plugin on the FastAPI app

### 4.1 Dockerfile changes (NMT/TTS)

In the NMT and TTS Dockerfiles you will find:

```dockerfile
COPY libs/dhruva_observability /app/libs/dhruva_observability
RUN pip install --no-cache-dir --user -e /app/libs/dhruva_observability
```

This is all that is required on the build side.

### 4.2 `main.py` changes – NMT service

Key parts of `services/nmt-service/main.py`:

```python
from fastapi import FastAPI
from dhruva_observability import ObservabilityPlugin, PluginConfig

app = FastAPI(..., lifespan=lifespan)

# Initialize Dhruva Observability Plugin
config = PluginConfig.from_env()
config.enabled = True
if not config.customers:
    config.customers = []        # optional, else derived from JWT/headers
if not config.apps:
    config.apps = ["nmt"]        # service identifier

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
```

What this does:

- Enables the plugin via configuration.  
- Registers middleware and routes for `/enterprise/metrics` and `/enterprise/health`.  
- Switches the service to **automatic** metrics – no manual metric calls in routers.

### 4.3 `main.py` changes – TTS service

Key parts of `services/tts-service/main.py`:

```python
from fastapi import FastAPI
from dhruva_observability import ObservabilityPlugin, PluginConfig

app = FastAPI(..., lifespan=lifespan)

config = PluginConfig.from_env()
config.enabled = True
if not config.customers:
    config.customers = []
if not config.apps:
    config.apps = ["tts"]

plugin = ObservabilityPlugin(config)
plugin.register_plugin(app)
```

The pattern is identical; only the `apps` list changes to reflect the service (“nmt”, “tts”, etc.).

### 4.4 ASR and other services

- NMT and TTS are already integrated with Dhruva.  
- ASR and other services can be integrated by repeating the **same two steps**:
  1. Add the `COPY` + `pip install -e` lines to the Dockerfile.  
  2. Import and register `ObservabilityPlugin` in `main.py` with `apps=["asr"]` (or the appropriate app name).

---

## 5. Prometheus & Grafana Configuration (Current State)

### 5.1 Prometheus scrape configuration

File: `infrastructure/prometheus/prometheus.yml`

- Standard service metrics:

```yaml
- job_name: "ai4i-services"
  scrape_interval: 5s
  metrics_path: /metrics
  static_configs:
    - targets:
        - "nmt-service:8089"
        - "tts-service:8088"
        - "asr-service:8087"
        - "llm-service:8090"
```

- Dhruva enterprise metrics (plugin):

```yaml
- job_name: "dhruva-enterprise"
  scrape_interval: 5s
  metrics_path: /enterprise/metrics
  static_configs:
    - targets:
        - "nmt-service:8089"
        - "tts-service:8088"
        - "asr-service:8087"
        - "llm-service:8090"
```

Important points:

- Prometheus talks to services on **container ports** (`8089`, `8088`, `8087`, `8090`).  
- Prometheus runs in the same Docker network, so it can use service names like `nmt-service`.  
- The Dhruva plugin metrics are all exposed under `/enterprise/metrics`.

### 5.2 Grafana datasource

File: `infrastructure/grafana/provisioning/datasources/prometheus.yaml`:

- Configures a single Prometheus datasource at `http://prometheus:9090`.  
- Grafana is reachable on `http://localhost:3001` (host) and uses this datasource to build dashboards.

Dashboards can be provisioned via JSON files under `infrastructure/grafana/provisioning/dashboards/` (for example, the devops and NMT dashboards).

---

## 6. Environment Variables

### 6.1 Dhruva plugin configuration

Core variables (read by `PluginConfig.from_env()`):

| Variable                  | Default              | Description                            |
|--------------------------|----------------------|----------------------------------------|
| `OBSERVE_UTIL_ENABLED`   | `false`              | Enable/disable plugin                  |
| `OBSERVE_UTIL_DEBUG`     | `false`              | Debug logging                          |
| `OBSERVE_UTIL_METRICS_PATH` | `/enterprise/metrics` | Metrics endpoint path              |
| `OBSERVE_UTIL_HEALTH_PATH`  | `/enterprise/health`  | Health endpoint path               |
| `OBSERVE_UTIL_CUSTOMERS` | (empty)              | Comma‑separated customers (optional)   |
| `OBSERVE_UTIL_APPS`      | (empty)              | Comma‑separated app names (optional)   |

Typical values in a `.env`:

```bash
OBSERVE_UTIL_ENABLED=true
OBSERVE_UTIL_DEBUG=false
OBSERVE_UTIL_CUSTOMERS=irctc,beml,kisanmitra
OBSERVE_UTIL_APPS=nmt,tts,asr
```

If `OBSERVE_UTIL_CUSTOMERS` or `OBSERVE_UTIL_APPS` are not set, the plugin derives values from JWTs, headers, and request paths where possible.

### 6.2 Prometheus & Grafana (via docker‑compose)

- Scrape interval and Prometheus options are set in `prometheus.yml`.  
- Grafana admin user/password and ports are set in `docker-compose.yml` (see project README for exact values).

---

## 7. How to Run and Verify End‑to‑End

### 7.1 Start core services with observability

From the project root:

```bash
docker compose up -d nmt-service tts-service asr-service llm-service prometheus grafana
```

Confirm Prometheus and Grafana are running:

```bash
docker compose ps prometheus grafana
```

### 7.2 Check metrics endpoints directly

From your host machine:

```bash
# NMT plugin metrics
curl http://localhost:8091/enterprise/metrics

# TTS plugin metrics
curl http://localhost:8088/enterprise/metrics
```

You should see many `telemetry_obsv_*` metrics in the output.

### 7.3 Generate some traffic

Example NMT inference:

```bash
curl -X POST http://localhost:8091/api/v1/nmt/inference \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"source": "Hello world"}],
    "config": {
      "serviceId": "ai4bharat/indictrans--gpu-t4",
      "language": {
        "sourceLanguage": "en",
        "targetLanguage": "hi"
      }
    }
  }'
```

Then check metrics again:

```bash
curl http://localhost:8091/enterprise/metrics | grep telemetry_obsv_nmt_characters_translated
```

### 7.4 Use Prometheus UI

Open `http://localhost:9090` and:

- Go to **Status → Targets** and check `ai4i-services` and `dhruva-enterprise` jobs are `UP`.  
- Use the **Graph** tab with queries such as:

```promql
telemetry_obsv_requests_total
telemetry_obsv_requests_total{app="nmt"}
telemetry_obsv_tts_characters_synthesized
rate(telemetry_obsv_requests_total[5m]) by (app)
```

### 7.5 Use Grafana

Open `http://localhost:3001`:

- Log in (default admin credentials from `docker-compose.yml`).  
- Verify the Prometheus datasource is healthy.  
- Import or open the dashboards under `infrastructure/grafana/provisioning/dashboards/`.  
- Add panels that query `telemetry_obsv_*` metrics.

---

## 8. Historical Note: From `ai4i_observability` to Dhruva Plugin

Originally, the project used a custom `ai4i_observability` package:

- Exposed `/metrics` and `/enterprise/metrics`.  
- Required **manual** metric calls, e.g. `record_translation(...)`, `record_tts_characters(...)`.  
- Metric names were prefixed with `ai4i_...` (for example, `ai4i_requests_total`).

The Dhruva Observability Plugin replaced this with:

- Automatic metric extraction from request bodies and headers.  
- New metric names with `telemetry_obsv_...` prefix.  
- A single, richer plugin shared across services and teams.

You may still see some legacy files related to `ai4i_observability` in the repo, but for new work you should:

- Use **Dhruva Observability Plugin** as described in this guide.  
- Prefer metrics with the `telemetry_obsv_` prefix in Prometheus and Grafana.  

---

## 9. If You Are Implementing This From Scratch

To recap the steps in the simplest possible checklist:

1. **Add the plugin to your service Dockerfile**
   - `COPY libs/dhruva_observability /app/libs/dhruva_observability`
   - `RUN pip install --no-cache-dir --user -e /app/libs/dhruva_observability`
2. **Register the plugin in your FastAPI `main.py`**
   - Import `ObservabilityPlugin` and `PluginConfig`  
   - Create config via `PluginConfig.from_env()`  
   - Set `config.enabled = True`, optionally set `apps=[...], customers=[...]`  
   - Call `plugin.register_plugin(app)`
3. **Ensure Prometheus scrapes `/enterprise/metrics`**
   - Update `infrastructure/prometheus/prometheus.yml` as shown above.  
4. **Point Grafana at Prometheus and build dashboards**
   - Use metric names starting with `telemetry_obsv_`.  

If you follow these four steps, you will have the same observability setup as the NMT and TTS services in this repository.


