# Hot Reload Development Setup

This guide explains how to develop with instant code changes without rebuilding Docker containers.

## Overview

The `docker-compose-local.yml` is configured with volume mounts that sync your local code into running containers. **All 20 Python (uvicorn) services** are started with `--reload` via a `command` override in the compose file, and the frontend uses `Dockerfile.dev` to run the Next.js dev server (`next dev`). Code changes are detected and the process restarts (or the dev server hot-reloads) automatically without rebuilding.

### Services with Hot Reload Enabled

All the following services have hot reload enabled:

**Core Services:**
- `api-gateway-service` (port 9000)
- `auth-service` (port 8081)
- `config-service` (port 8082)
- `docs-manager` (port 8103)
- `telemetry-service` (port 8084)
- `alerting-service` (port 8085)

**ML/AI Services:**
- `asr-service` (port 8087)
- `tts-service` (port 8088)
- `nmt-service` (port 8091)
- `ocr-service` (port 8099)
- `ner-service` (port 9001)
- `llm-service` (port 8093)
- `pipeline-service` (port 8092)
- `transliteration-service` (port 8097)
- `language-detection-service` (port 8098)
- `audio-lang-detection-service` (port 8096)
- `speaker-diarization-service` (port 8095)
- `language-diarization-service` (port 9002)

**Infrastructure Services:**
- `model-management-service` (port 8094)
- `multi-tenant-service` (port 8100)

## Quick Start

### 1. Initial Setup (One Time)
```bash
# Build all services (only needed once or when dependencies change)
docker compose -f docker-compose-local.yml build

# Start all services
docker compose -f docker-compose-local.yml up
```

### 2. Development Workflow
- **Edit Code**: Make changes to any Python file in `services/`, `infrastructure/`, or `shared/`
- **Auto-Reload**: The service automatically detects changes and reloads
- **No Rebuild Needed**: Changes are instant!

### 3. How to Test Hot Reload

1. **Start one service** (or all) and note its health URL:
   ```bash
   docker compose -f docker-compose-local.yml up -d docs-manager
   ```

2. **Call the health endpoint** and note the response:
   ```bash
   curl -s http://localhost:8103/health
   # e.g. {"status":"ok","service":"docs-manager"}
   ```

3. **Change code** (e.g. in `services/docs-manager/main.py`): temporarily change the health response string (e.g. add `"hot-reload": true` or change the message).

4. **Save the file.** Within a few seconds uvicorn should reload (watch logs if you want):
   ```bash
   docker compose -f docker-compose-local.yml logs -f docs-manager
   # Look for: "WatchFiles detected changes" or "Reloading..."
   ```

5. **Call the health endpoint again** (no rebuild, no restart):
   ```bash
   curl -s http://localhost:8103/health
   ```
   You should see your updated response. Revert the test change when done.

**Frontend:** For `simple-ui-frontend`, edit a page under `frontend/simple-ui/`, save, and refresh the browser — the Next.js dev server will hot-reload.

### 4. Verify Hot Reload is Enabled

To check if a service has hot reload enabled:

```bash
# Check if --reload is in the process
docker top ai4v-<service-name> | grep "\-\-reload"

# Or check logs for reload indicator
docker logs ai4v-<service-name> | grep -i "reload\|watchfiles"
# Should show: "INFO:     Started reloader process [X] using WatchFiles"
```

### 5. Working with Specific Services
```bash
# View logs for a specific service
docker compose -f docker-compose-local.yml logs -f <service-name>

# Restart a single service (if auto-reload doesn't work)
docker compose -f docker-compose-local.yml restart <service-name>

# Force recreate to ensure hot reload is enabled
docker compose -f docker-compose-local.yml up -d --force-recreate <service-name>

# Stop all services
docker compose -f docker-compose-local.yml down
```

## When Do You Need to Rebuild?

Rebuild is ONLY required when:
- ✅ Adding new dependencies (`requirements.txt`, `package.json`)
- ✅ Changing `Dockerfile` configurations
- ✅ Modifying environment variables in `.env` files
- ✅ Installing system packages or libraries
- ✅ Before pushing to production

```bash
# Rebuild specific service
docker compose -f docker-compose-local.yml build <service-name>

# Rebuild and restart
docker compose -f docker-compose-local.yml up --build <service-name>
```

## Volume Mounts Explained

### Python Services
```yaml
volumes:
  - ./services/<service-name>:/app
  - ./libs/ai4icore_*:/app/libs/ai4icore_*
  - ./services/constants:/app/services/constants
  - ./services/multi-tenant-feature:/app/services/multi-tenant-feature
  - ./infrastructure:/app/infrastructure
  - ./shared:/app/shared
```

### Frontend (Next.js)
The frontend uses `Dockerfile.dev` (not the production Dockerfile) so the container runs the Next.js **dev server** (`next dev`) instead of the standalone `server.js`. That way the volume mount does not hide the entry point and hot reload works.

```yaml
volumes:
  - ./frontend/simple-ui:/app
  - /app/node_modules  # Excluded to prevent conflicts
  - /app/.next         # Excluded to prevent conflicts
```

## Troubleshooting

### Code changes not reflecting?
1. **Verify hot reload is enabled:**
   ```bash
   docker top ai4v-<service-name> | grep "\-\-reload"
   # Should show: uvicorn ... --reload
   ```

2. **Force recreate the service** to ensure hot reload is active:
   ```bash
   docker compose -f docker-compose-local.yml up -d --force-recreate <service-name>
   ```

3. **Check logs for reload messages:**
   ```bash
   docker compose -f docker-compose-local.yml logs -f <service-name>
   # Look for: "WatchFiles detected changes" or "Reloading..."
   ```

4. **Restart the specific service:**
   ```bash
   docker compose -f docker-compose-local.yml restart <service-name>
   ```

### Permission errors?
```bash
# Fix file permissions (macOS/Linux)
sudo chown -R $USER:$USER .

# On macOS, if you see extended attribute errors:
xattr -d com.apple.provenance <file-or-directory>
```

### Container crashes after code change?
- **Syntax error in your code** - check the logs: `docker logs ai4v-<service-name>`
- **Missing dependency** - rebuild the container: `docker compose -f docker-compose-local.yml build <service-name>`

### Service not starting with hot reload?
If a service was started before hot reload was configured, force recreate it:
```bash
docker compose -f docker-compose-local.yml up -d --force-recreate <service-name>
```

## Benefits

- ⚡ **Fast Development**: No waiting for builds
- 🔄 **Instant Feedback**: See changes immediately (typically within 1-3 seconds)
- 💰 **Save Time**: Hours saved on rebuilds
- 🎯 **Focused Testing**: Quick iterations on features
- 📦 **20 Services Ready**: All Python services configured for hot reload out of the box

## Verification Script

To check all services at once:

```bash
#!/bin/bash
# Check all services with hot reload (portable version)

services=(
  "api-gateway-service:ai4v-api-gateway"
  "auth-service:ai4v-auth-service"
  "config-service:ai4v-config-service"
  "docs-manager:ai4v-docs-manager"
  "telemetry-service:ai4v-telemetry-service"
  "alerting-service:ai4v-alerting-service"
  "asr-service:ai4v-asr-service"
  "tts-service:ai4v-tts-service"
  "nmt-service:ai4v-nmt-service"
  "ocr-service:ai4v-ocr-service"
  "ner-service:ai4v-ner-service"
  "llm-service:ai4v-llm-service"
  "pipeline-service:ai4v-pipeline-service"
  "model-management-service:ai4v-model-management-service"
  "multi-tenant-service:ai4v-multi-tenant-service"
  "transliteration-service:ai4v-transliteration-service"
  "language-detection-service:ai4v-language-detection-service"
  "audio-lang-detection-service:ai4v-audio-lang-detection-service"
  "speaker-diarization-service:ai4v-speaker-diarization-service"
  "language-diarization-service:ai4v-language-diarization-service"
)

echo "Service                              Status                    Hot Reload"
echo "----------------------------------------------------------------------------"

for svc_pair in "${services[@]}"; do
  service=$(echo "$svc_pair" | cut -d: -f1)
  container=$(echo "$svc_pair" | cut -d: -f2)
  
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    reload=$(docker top "${container}" 2>/dev/null | grep -q "\-\-reload" && echo "✅ Enabled" || echo "❌ Disabled")
    status=$(docker ps --filter "name=${container}" --format "{{.Status}}" | head -1 | cut -d' ' -f1-3)
    printf "%-40s %-25s %s\n" "$service" "$status" "$reload"
  else
    printf "%-40s %-25s %s\n" "$service" "NOT RUNNING" "❌"
  fi
done
```

Save this as `check-hot-reload.sh`, make it executable (`chmod +x check-hot-reload.sh`), and run it to see the status of all services.

## Production Deployment

Before deploying to production:
```bash
# Full clean rebuild
docker compose -f docker-compose-local.yml down -v
docker compose -f docker-compose-local.yml build --no-cache
docker compose -f docker-compose-local.yml up
```

Test thoroughly to ensure all changes work correctly in a fresh build!
