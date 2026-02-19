# Hot Reload Development Setup

This guide explains how to develop with instant code changes without rebuilding Docker containers.

## Overview

The `docker-compose-local.yml` is configured with volume mounts that sync your local code into running containers. All Python (uvicorn) services are started with `--reload` via a `command` override in the compose file, and the frontend uses `Dockerfile.dev` to run the Next.js dev server (`next dev`). Code changes are detected and the process restarts (or the dev server hot-reloads) automatically without rebuilding.

## Quick Start

### 1. Initial Setup (One Time)
```bash
# Build all services (only needed once or when dependencies change)
docker-compose -f docker-compose-local.yml build

# Start all services
docker-compose -f docker-compose-local.yml up
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
   # Look for: "Watching for file changes" or "Detected file change, reloading"
   ```

5. **Call the health endpoint again** (no rebuild, no restart):
   ```bash
   curl -s http://localhost:8103/health
   ```
   You should see your updated response. Revert the test change when done.

**Frontend:** For `simple-ui-frontend`, edit a page under `frontend/simple-ui/`, save, and refresh the browser — the Next.js dev server will hot-reload.

### 4. Working with Specific Services
```bash
# View logs for a specific service
docker-compose -f docker-compose-local.yml logs -f <service-name>

# Restart a single service (if auto-reload doesn't work)
docker-compose -f docker-compose-local.yml restart <service-name>

# Stop all services
docker-compose -f docker-compose-local.yml down
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
docker-compose -f docker-compose-local.yml build <service-name>

# Rebuild and restart
docker-compose -f docker-compose-local.yml up --build <service-name>
```

## Volume Mounts Explained

### Python Services
```yaml
volumes:
  - ./services/<service-name>:/app/services/<service-name>
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
1. Check if the service has auto-reload enabled (most Python frameworks do)
2. Restart the specific service: `docker-compose -f docker-compose-local.yml restart <service-name>`
3. Check logs for errors: `docker-compose -f docker-compose-local.yml logs -f <service-name>`

### Permission errors?
```bash
# Fix file permissions (macOS/Linux)
sudo chown -R $USER:$USER .
```

### Container crashes after code change?
- Syntax error in your code - check the logs
- Missing dependency - rebuild the container

## Benefits

- ⚡ **Fast Development**: No waiting for builds
- 🔄 **Instant Feedback**: See changes immediately
- 💰 **Save Time**: Hours saved on rebuilds
- 🎯 **Focused Testing**: Quick iterations on features

## Production Deployment

Before deploying to production:
```bash
# Full clean rebuild
docker-compose -f docker-compose-local.yml down -v
docker-compose -f docker-compose-local.yml build --no-cache
docker-compose -f docker-compose-local.yml up
```

Test thoroughly to ensure all changes work correctly in a fresh build!
