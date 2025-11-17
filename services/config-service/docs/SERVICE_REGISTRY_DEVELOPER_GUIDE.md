# Service Registry Developer Guide

**For developers creating new microservices in this project**

This guide shows you how to implement service registry/discovery in your new microservice. Follow these steps in order.

---

## What You'll Get

After completing this guide, your service will:
- ✅ Automatically register itself when it starts
- ✅ Be discoverable by other services
- ✅ Automatically deregister when it shuts down
- ✅ Support service discovery for calling other services

---

## Step 1: Create the Service Registry Client

Create `utils/service_registry_client.py` in your service directory:

```python
import os
import logging
from typing import Optional, Dict, Any

import httpx
import asyncio


logger = logging.getLogger(__name__)


class ServiceRegistryHttpClient:
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
        payload = {
            "service_name": service_name,
            "service_url": service_url,
            "health_check_url": health_check_url,
            "service_metadata": service_metadata or {},
        }
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
                    resp = await client.post(f"{self._registry_base}/register", json=payload)
                resp.raise_for_status()
                data = resp.json() or {}
                return data.get("instance_id")
        except Exception as e:
            logger.warning("Service registry registration failed: %s", e)
            return None

    async def deregister(self, service_name: str, instance_id: str, request_timeout_s: float = 5.0) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
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
        try:
            async with httpx.AsyncClient() as client:
                async with asyncio.timeout(request_timeout_s):
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

---

## Step 2: Add httpx to requirements.txt

Add this line to your `requirements.txt`:

```txt
httpx>=0.24.0
```

---

## Step 3: Update main.py - Add Registration Code

In your `main.py`, add the registration code to your FastAPI lifespan function.

### 3a. Add imports at the top:

```python
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI

from utils.service_registry_client import ServiceRegistryHttpClient

logger = logging.getLogger(__name__)

# Global variables for registry
registry_client: Optional[ServiceRegistryHttpClient] = None
registered_instance_id: Optional[str] = None
```

### 3b. Add registration in startup (inside your lifespan function):

Add this code **at the end of your startup logic**, before `yield`:

```python
# Register service in central registry via config-service
try:
    global registry_client, registered_instance_id
    registry_client = ServiceRegistryHttpClient()
    service_name = os.getenv("SERVICE_NAME", "your-service-name")
    service_port = int(os.getenv("SERVICE_PORT", "8090"))
    
    # Determine service URL
    public_base_url = os.getenv("SERVICE_PUBLIC_URL")
    if public_base_url:
        service_url = public_base_url.rstrip("/")
    else:
        service_host = os.getenv("SERVICE_HOST", service_name)
        service_url = f"http://{service_host}:{service_port}"
    
    health_url = service_url + "/health"
    instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
    
    registered_instance_id = await registry_client.register(
        service_name=service_name,
        service_url=service_url,
        health_check_url=health_url,
        service_metadata={"instance_id": instance_id, "status": "healthy"},
    )
    
    if registered_instance_id:
        logger.info("Registered %s with service registry as instance %s", service_name, registered_instance_id)
    else:
        logger.warning("Service registry registration skipped/failed for %s", service_name)
except Exception as e:
    logger.warning("Service registry registration error: %s", e)
```

### 3c. Add deregistration in shutdown (after `yield`):

Add this code **in your shutdown logic**, after `yield`:

```python
# Deregister from registry if previously registered
try:
    global registry_client, registered_instance_id
    if registry_client and registered_instance_id:
        service_name = os.getenv("SERVICE_NAME", "your-service-name")
        await registry_client.deregister(service_name, registered_instance_id)
        logger.info("Deregistered %s from service registry", service_name)
except Exception as e:
    logger.warning("Service registry deregistration error: %s", e)
```

### Complete Example:

Here's how your lifespan function should look:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Your Service...")
    
    try:
        # Your existing startup code here...
        # (database connections, initialization, etc.)
        
        # Register service in central registry via config-service
        try:
            global registry_client, registered_instance_id
            registry_client = ServiceRegistryHttpClient()
            service_name = os.getenv("SERVICE_NAME", "your-service-name")
            service_port = int(os.getenv("SERVICE_PORT", "8090"))
            
            public_base_url = os.getenv("SERVICE_PUBLIC_URL")
            if public_base_url:
                service_url = public_base_url.rstrip("/")
            else:
                service_host = os.getenv("SERVICE_HOST", service_name)
                service_url = f"http://{service_host}:{service_port}"
            
            health_url = service_url + "/health"
            instance_id = os.getenv("SERVICE_INSTANCE_ID", f"{service_name}-{os.getpid()}")
            
            registered_instance_id = await registry_client.register(
                service_name=service_name,
                service_url=service_url,
                health_check_url=health_url,
                service_metadata={"instance_id": instance_id, "status": "healthy"},
            )
            
            if registered_instance_id:
                logger.info("Registered %s with service registry as instance %s", service_name, registered_instance_id)
            else:
                logger.warning("Service registry registration skipped/failed for %s", service_name)
        except Exception as e:
            logger.warning("Service registry registration error: %s", e)
        
        logger.info("Your Service started successfully")
    except Exception as e:
        logger.error(f"Failed to start Your Service: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Your Service...")
    
    try:
        # Deregister from registry if previously registered
        try:
            global registry_client, registered_instance_id
            if registry_client and registered_instance_id:
                service_name = os.getenv("SERVICE_NAME", "your-service-name")
                await registry_client.deregister(service_name, registered_instance_id)
                logger.info("Deregistered %s from service registry", service_name)
        except Exception as e:
            logger.warning("Service registry deregistration error: %s", e)
    finally:
        logger.info("Your Service shutdown complete")


app = FastAPI(lifespan=lifespan)
```

---

## Step 4: Ensure Health Endpoint Exists

Make sure your service has a `/health` endpoint. If not, add it:

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

---

## Step 5: Set Environment Variables

Create or update `env.template` in your service directory:

```bash
# Required
SERVICE_NAME=your-service-name
SERVICE_PORT=8090
SERVICE_HOST=your-service-name

# Optional
SERVICE_PUBLIC_URL=
SERVICE_INSTANCE_ID=
CONFIG_SERVICE_URL=http://config-service:8082
```

**Important:** Replace `your-service-name` with your actual service name.

---

## Step 6: Update docker-compose.yml

Add your service to `docker-compose.yml` with these environment variables:

```yaml
your-service-name:
  build:
    context: ./services/your-service-name
    dockerfile: Dockerfile
  container_name: ai4v-your-service-name
  ports:
    - "8090:8090"
  environment:
    - SERVICE_NAME=your-service-name
    - SERVICE_PORT=8090
    - SERVICE_HOST=your-service-name
    - CONFIG_SERVICE_URL=http://config-service:8082
  env_file:
    - ./services/your-service-name/.env
  depends_on:
    config-service:
      condition: service_healthy
  networks:
    - microservices-network
  restart: unless-stopped
```

---

## Step 7: Using Service Discovery (Optional)

To discover and call other services from your service:

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

---

## Verification Checklist

After implementation, verify:

- [ ] `utils/service_registry_client.py` exists
- [ ] `httpx>=0.24.0` in `requirements.txt`
- [ ] Registration code added in lifespan startup
- [ ] Deregistration code added in lifespan shutdown
- [ ] `/health` endpoint exists
- [ ] Environment variables set in `env.template`
- [ ] Service added to `docker-compose.yml` with correct env vars

---

## Testing

1. **Start your service:**
   ```bash
   docker compose up your-service-name
   ```

2. **Check logs for registration:**
   ```bash
   docker compose logs your-service-name | grep -i register
   ```
   You should see: `"Registered your-service-name with service registry as instance ..."`

3. **Verify registration:**
   ```bash
   curl http://localhost:8082/api/v1/registry/services/your-service-name
   ```

4. **Test service discovery:**
   ```bash
   curl http://localhost:8082/api/v1/registry/services/your-service-name/url
   ```

---

## Common Issues

**Registration fails silently:**
- Check `CONFIG_SERVICE_URL` is correct
- Verify Config Service is running: `curl http://config-service:8082/health`
- Check service logs for warnings

**Service not discoverable:**
- Verify registration succeeded (check logs)
- Ensure `/health` endpoint returns 200
- Verify `service_url` in registration is correct

**Connection refused:**
- Ensure both services are on `microservices-network`
- Verify `CONFIG_SERVICE_URL` uses `config-service` (not `localhost`)

---

## That's It!

Your service is now integrated with the service registry. It will automatically register on startup and deregister on shutdown. Other services can discover and call your service using the registry client.

**Need help?** Check existing implementations:
- `services/asr-service/main.py`
- `services/nmt-service/main.py`
- `services/tts-service/main.py`
- `services/pipeline-service/main.py`

