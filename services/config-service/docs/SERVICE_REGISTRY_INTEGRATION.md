# Service Registry Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [How Service Registry Works](#how-service-registry-works)
3. [Integration Steps](#integration-steps)
4. [Code Implementation](#code-implementation)
5. [Environment Variables](#environment-variables)
6. [Service Discovery](#service-discovery)
7. [Testing](#testing)
8. [Troubleshooting](#troubleshooting)

---

## Overview

The Service Registry is a centralized service discovery mechanism that allows microservices to:
- **Register themselves** when they start up
- **Discover other services** dynamically
- **Maintain service health** information
- **Automatically remove** crashed services from the registry

The registry is managed by the **Config Service** and uses:
- **ZooKeeper** for real-time service discovery with ephemeral nodes
- **PostgreSQL** for persistent storage and audit trail
- **Redis** for caching service information

---

## How Service Registry Works

### Architecture Flow

```
┌─────────────────┐
│  Microservice   │
│    (Starts)     │
└────────┬────────┘
         │
         │ 1. Reads environment variables
         │    (SERVICE_NAME, SERVICE_PORT, etc.)
         │
         ▼
┌─────────────────┐
│ Construct URL   │
│ http://host:port│
└────────┬────────┘
         │
         │ 2. POST /api/v1/registry/register
         │
         ▼
┌─────────────────┐      ┌──────────────┐      ┌─────────────┐
│  Config Service │──────▶│  ZooKeeper   │      │  PostgreSQL │
│                 │       │ (Ephemeral)  │      │  (Persist)  │
└─────────────────┘      └──────────────┘      └─────────────┘
         │
         │ 3. Returns instance_id
         │
         ▼
┌─────────────────┐
│  Microservice   │
│  (Registered)   │
└─────────────────┘
```

### Key Concepts

1. **Self-Registration**: Each microservice determines its own location from environment variables and registers itself
2. **Ephemeral Nodes**: ZooKeeper creates ephemeral nodes that automatically disappear if the service crashes
3. **Dual Storage**: Services are stored in both ZooKeeper (for discovery) and PostgreSQL (for audit)
4. **Health Checks**: The registry can monitor service health via health check URLs

---

## Integration Steps

To integrate your new microservice with the Service Registry, follow these steps:

### Step 1: Create Service Registry Client

Create a file `utils/service_registry_client.py` in your service:

```python
import os
import logging
from typing import Optional, Dict, Any

import httpx


logger = logging.getLogger(__name__)


class ServiceRegistryHttpClient:
    """HTTP client for interacting with the Config Service's registry API."""
    
    def __init__(self) -> None:
        base_url = os.getenv("CONFIG_SERVICE_URL", "http://config-service:8082")
        self._registry_base = base_url.rstrip("/") + "/api/v1/registry"

    async def register(
        self,
        service_name: str,
        service_url: str,
        health_check_url: Optional[str],
        service_metadata: Optional[Dict[str, Any]] = None,
        request_timeout_s: float = 5.0,
    ) -> Optional[str]:
        """
        Register this service instance with the service registry.
        
        Args:
            service_name: Name of the service (e.g., "my-service")
            service_url: Base URL where this service is accessible
            health_check_url: URL for health check endpoint
            service_metadata: Optional metadata dictionary
            request_timeout_s: Request timeout in seconds
            
        Returns:
            instance_id if registration successful, None otherwise
        """
        payload = {
            "service_name": service_name,
            "service_url": service_url,
            "health_check_url": health_check_url,
            "service_metadata": service_metadata or {},
        }
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.post(f"{self._registry_base}/register", json=payload)
            resp.raise_for_status()
            data = resp.json() or {}
            return data.get("instance_id")
        except Exception as e:
            logger.warning("Service registry registration failed: %s", e)
            return None

    async def deregister(self, service_name: str, instance_id: str, request_timeout_s: float = 5.0) -> bool:
        """
        Deregister this service instance from the service registry.
        
        Args:
            service_name: Name of the service
            instance_id: Instance ID returned from register()
            request_timeout_s: Request timeout in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.post(
                    f"{self._registry_base}/deregister",
                    params={"service_name": service_name, "instance_id": instance_id},
                )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("Service registry deregistration failed: %s", e)
            return False

    async def discover_url(self, service_name: str, request_timeout_s: float = 3.0) -> Optional[str]:
        """
        Discover a healthy instance URL for a service.
        
        Args:
            service_name: Name of the service to discover
            request_timeout_s: Request timeout in seconds
            
        Returns:
            URL of a healthy instance, or None if not found
        """
        try:
            async with httpx.AsyncClient(timeout=request_timeout_s) as client:
                resp = await client.get(f"{self._registry_base}/services/{service_name}/url")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json() or {}
            return data.get("url")
        except Exception as e:
            logger.warning("Service discovery failed for %s: %s", service_name, e)
            return None
```

### Step 2: Add Dependencies

Add `httpx` to your `requirements.txt`:

```txt
httpx>=0.24.0
```

### Step 3: Implement Registration in Startup

In your service's `main.py`, add registration logic in the FastAPI `lifespan` function:

```python
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from utils.service_registry_client import ServiceRegistryHttpClient

logger = logging.getLogger(__name__)

# Global variables to track registration state
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown"""
    
    # Startup
    logger.info("Starting My Service...")
    
    try:
        # Your existing startup code here...
        
        # Register service in central registry via config-service
        try:
            global registry_client, registered_instance_id
            
            registry_client = ServiceRegistryHttpClient()
            
            # Get service configuration from environment variables
            service_name = os.getenv("SERVICE_NAME", "my-service")
            service_port = int(os.getenv("SERVICE_PORT", "8090"))
            
            # Determine service URL
            # Option 1: Use explicit public URL if provided (for external access)
            public_base_url = os.getenv("SERVICE_PUBLIC_URL")
            if public_base_url:
                service_url = public_base_url.rstrip("/")
            else:
                # Option 2: Construct from host and port (for Docker networking)
                service_host = os.getenv("SERVICE_HOST", service_name)
                service_url = f"http://{service_host}:{service_port}"
            
            # Health check URL
            health_url = service_url + "/health"  # Adjust path if different
            
            # Instance ID (optional - will be auto-generated if not provided)
            instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
            
            # Register with service registry
            registered_instance_id = await registry_client.register(
                service_name=service_name,
                service_url=service_url,
                health_check_url=health_url,
                service_metadata={
                    "instance_id": instance_id,
                    "status": "healthy",
                    # Add any other metadata here
                },
            )
            
            if registered_instance_id:
                logger.info(
                    "Registered %s with service registry as instance %s",
                    service_name,
                    registered_instance_id
                )
            else:
                logger.warning(
                    "Service registry registration skipped/failed for %s",
                    service_name
                )
                
        except Exception as e:
            logger.warning("Service registry registration error: %s", e)
        
        logger.info("My Service started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start My Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down My Service...")
    
    try:
        # Deregister from registry if previously registered
        try:
            global registry_client, registered_instance_id
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "my-service")
                await registry_client.deregister(service_name, registered_instance_id)
                logger.info("Deregistered %s from service registry", service_name)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)
    finally:
        logger.info("My Service shutdown complete")


# Create FastAPI application
app = FastAPI(lifespan=lifespan)

# Your routes here...
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

# ... rest of your application
```

### Step 4: Create Environment Template

Create or update `env.template` in your service directory:

```bash
SERVICE_NAME=my-service
SERVICE_PORT=8090
SERVICE_HOST=my-service
SERVICE_PUBLIC_URL=
SERVICE_INSTANCE_ID=
CONFIG_SERVICE_URL=http://config-service:8082
```

### Step 5: Update Docker Compose

Add your service to `docker-compose.yml` with appropriate environment variables:

```yaml
my-service:
  build:
    context: ./services/my-service
    dockerfile: Dockerfile
  container_name: ai4v-my-service
  ports:
    - "8090:8090"
  environment:
    - SERVICE_NAME=my-service
    - SERVICE_PORT=8090
    - SERVICE_HOST=my-service
    - CONFIG_SERVICE_URL=http://config-service:8082
  env_file:
    - ./services/my-service/.env
  depends_on:
    config-service:
      condition: service_healthy
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  networks:
    - microservices-network
  restart: unless-stopped
```

---

## Code Implementation

### Complete Example: Minimal Integration

Here's a complete minimal example of a service with registry integration:

```python
# main.py
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI

from utils.service_registry_client import ServiceRegistryHttpClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting My Service...")
    
    try:
        # Register with service registry
        global registry_client, registered_instance_id
        registry_client = ServiceRegistryHttpClient()
        
        service_name = os.getenv("SERVICE_NAME", "my-service")
        service_port = int(os.getenv("SERVICE_PORT", "8090"))
        service_host = os.getenv("SERVICE_HOST", service_name)
        service_url = f"http://{service_host}:{service_port}"
        
        registered_instance_id = await registry_client.register(
            service_name=service_name,
            service_url=service_url,
            health_check_url=f"{service_url}/health",
            service_metadata={"status": "healthy"},
        )
        
        if registered_instance_id:
            logger.info(f"Registered as {registered_instance_id}")
        
    except Exception as e:
        logger.warning(f"Registration failed: {e}")
    
    yield
    
    # Shutdown
    if registry_client and registered_instance_id:
        try:
            service_name = os.getenv("SERVICE_NAME", "my-service")
            await registry_client.deregister(service_name, registered_instance_id)
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {"service": "my-service"}
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example | Default |
|----------|-------------|---------|---------|
| `SERVICE_NAME` | Unique name of your service | `my-service` | Required |
| `SERVICE_PORT` | Port your service listens on | `8090` | Required |
| `SERVICE_HOST` | Hostname for service URL (Docker container name) | `my-service` | `SERVICE_NAME` |

### Optional Variables

| Variable | Description | Example | When to Use |
|----------|-------------|---------|-------------|
| `SERVICE_PUBLIC_URL` | Full public URL if different from Docker networking | `https://api.example.com` | External access, different protocol |
| `SERVICE_INSTANCE_ID` | Custom instance identifier | `my-service-001` | Multiple instances, custom IDs |
| `CONFIG_SERVICE_URL` | Config service endpoint | `http://config-service:8082` | `http://config-service:8082` |

### How URL Construction Works

The service URL is determined in this priority:

1. **If `SERVICE_PUBLIC_URL` is set**: Use it directly
2. **Otherwise**: Construct as `http://{SERVICE_HOST}:{SERVICE_PORT}`

**Examples:**
- Docker internal networking: `SERVICE_HOST=my-service`, `SERVICE_PORT=8090` → `http://my-service:8090`
- External access: `SERVICE_PUBLIC_URL=https://api.example.com/my-service` → `https://api.example.com/my-service`

### Docker Networking

In Docker Compose, services can reach each other using their service names. For example:
- `SERVICE_HOST=my-service` allows other services to reach it at `http://my-service:8090`
- This works because Docker Compose creates a network where service names resolve to containers

---

## Service Discovery

### Discovering Other Services

To discover and call other services, use the registry client:

```python
from utils.service_registry_client import ServiceRegistryHttpClient

async def call_another_service():
    registry_client = ServiceRegistryHttpClient()
    
    # Discover a healthy instance of another service
    asr_service_url = await registry_client.discover_url("asr-service")
    
    if asr_service_url:
        # Make HTTP call to discovered service
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{asr_service_url}/api/v1/asr/endpoint")
            return response.json()
    else:
        raise Exception("ASR service not available")
```

### Registry API Endpoints

The Config Service exposes these endpoints for service discovery:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/registry/services/{service_name}` | GET | Get all instances of a service |
| `/api/v1/registry/services/{service_name}/url` | GET | Get a random healthy instance URL |
| `/api/v1/registry/discover/{service_name}` | GET | Discover all healthy instances |
| `/api/v1/registry/services` | GET | List all registered services |

**Example:**
```bash
# Get all instances of asr-service
curl http://config-service:8082/api/v1/registry/services/asr-service

# Get a healthy instance URL
curl http://config-service:8082/api/v1/registry/services/asr-service/url
```

---

## Testing

### Test Registration Locally

1. **Start dependencies:**
```bash
docker compose up -d postgres redis zookeeper config-service
```

2. **Set environment variables:**
```bash
export SERVICE_NAME=my-service
export SERVICE_PORT=8090
export SERVICE_HOST=localhost
export CONFIG_SERVICE_URL=http://localhost:8082
```

3. **Run your service:**
```bash
python main.py
# or
uvicorn main:app --port 8090
```

4. **Verify registration:**
```bash
# List all services
curl http://localhost:8082/api/v1/registry/services

# Check your service specifically
curl http://localhost:8082/api/v1/registry/services/my-service
```

### Test in Docker

1. **Start all services:**
```bash
docker compose up -d
```

2. **Check logs for registration:**
```bash
docker compose logs my-service | grep -i register
```

3. **Verify via Config Service:**
```bash
docker compose exec config-service curl http://localhost:8082/api/v1/registry/services
```

---

## Troubleshooting

### Common Issues

#### 1. Registration Fails Silently

**Symptom**: No error but service not registered

**Solution**:
- Check `CONFIG_SERVICE_URL` is correct
- Verify Config Service is running: `curl http://config-service:8082/health`
- Check service logs for warnings
- Ensure network connectivity between services

#### 2. "Connection Refused" Errors

**Symptom**: Cannot connect to Config Service

**Solutions**:
- Verify Config Service is healthy: `docker compose ps config-service`
- Check network: Ensure both services are on `microservices-network`
- Verify `CONFIG_SERVICE_URL` uses correct hostname (`config-service`, not `localhost`)

#### 3. Service Not Discoverable

**Symptom**: Other services can't find your service

**Solutions**:
- Verify registration succeeded: Check logs for "Registered" message
- Check health endpoint is accessible: `curl http://my-service:8090/health`
- Verify `service_url` in registration is correct and reachable
- Check ZooKeeper connection: `docker compose logs zookeeper`

#### 4. Wrong Service URL

**Symptom**: Registered URL doesn't work

**Solutions**:
- For Docker networking: Use `SERVICE_HOST=my-service` (container name)
- For external access: Set `SERVICE_PUBLIC_URL` explicitly
- Verify port mapping: `docker compose ps` shows port mappings

#### 5. Health Check Fails

**Symptom**: Service registered but marked unhealthy

**Solutions**:
- Implement `/health` endpoint in your service
- Verify health endpoint returns 200 status
- Check health check URL matches actual endpoint

### Debug Checklist

- [ ] Config Service is running and healthy
- [ ] ZooKeeper is running and connected
- [ ] Environment variables are set correctly
- [ ] Service can reach Config Service (test: `curl http://config-service:8082/health`)
- [ ] Registration code executes during startup
- [ ] Service health endpoint works
- [ ] Service URL is correct for your deployment (Docker vs external)

### Logging

Enable debug logging to see registry activity:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Look for these log messages:
- `"Registered {service_name} with service registry as instance {instance_id}"` - Success
- `"Service registry registration skipped/failed"` - Failure
- `"Service registry registration error"` - Exception occurred

---

## Best Practices

1. **Graceful Degradation**: Don't fail startup if registration fails; log a warning instead
2. **Health Endpoints**: Always implement a `/health` endpoint for registry health checks
3. **Metadata**: Include useful metadata (version, region, etc.) in registration
4. **Deregistration**: Always deregister during shutdown (in `lifespan` shutdown)
5. **Error Handling**: Wrap registration in try-except to prevent startup failures
6. **Instance IDs**: Use meaningful instance IDs if running multiple instances
7. **Network Configuration**: Use service names (not IPs) for Docker networking

---

## Additional Resources

- **Config Service README**: `services/config-service/README.md`
- **Example Implementations**: 
  - `services/asr-service/main.py`
  - `services/nmt-service/main.py`
  - `services/tts-service/main.py`
  - `services/pipeline-service/main.py`

---

## Summary

Integrating with the Service Registry requires:

1. ✅ Create `utils/service_registry_client.py` 
2. ✅ Add `httpx` to `requirements.txt`
3. ✅ Register in `lifespan` startup function
4. ✅ Deregister in `lifespan` shutdown function
5. ✅ Set environment variables (`SERVICE_NAME`, `SERVICE_PORT`, `SERVICE_HOST`)
6. ✅ Implement `/health` endpoint
7. ✅ Add service to `docker-compose.yml` with proper dependencies

Once integrated, your service will:
- Automatically register on startup
- Be discoverable by other services
- Automatically remove itself from registry on shutdown
- Be monitored for health by the registry

