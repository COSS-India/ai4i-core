# AI4ICore Multi-Tenant Plugin

Shared multi-tenancy logic for AI4ICore inference services. Provides tenant context resolution, schema routing, and tenant-aware database sessions.

## Features

- **Tenant Context** - Resolve tenant from JWT or via API Gateway
- **Tenant Schema Router** - Route DB connections to tenant-specific schemas
- **Tenant DB Session** - Get tenant or shared auth_db session
- **Tenant Middleware** - Mark paths for tenant context extraction
- **Plugin Pattern** - One-line registration like observability/model-management

## Installation

```bash
cd libs/ai4icore_multi_tenant
pip install -e .
```

## Quick Start

```python
from fastapi import FastAPI, Depends, Request
from ai4icore_multi_tenant import (
    MultiTenantPlugin,
    MultiTenantConfig,
    get_tenant_db_session_factory,
    try_get_tenant_context,
)

app = FastAPI()

# Configure and register plugin
config = MultiTenantConfig.from_env()
config.tenant_paths = ["/api/v1/nmt"]  # Paths needing tenant context
plugin = MultiTenantPlugin(config)
plugin.register_plugin(
    app,
    db_session_factory=db_session_factory,
    multi_tenant_db_url=os.getenv("MULTI_TENANT_DB_URL"),
)

# In routes: use dependency
get_tenant_db_session = get_tenant_db_session_factory(config.api_gateway_url)

@app.post("/api/v1/nmt/inference")
async def inference(request: Request, db: AsyncSession = Depends(get_tenant_db_session)):
    tenant_context = await try_get_tenant_context(request, config.api_gateway_url)
    # ... use db (tenant schema or shared)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_GATEWAY_URL` | `http://api-gateway-service:8080` | API Gateway for tenant resolution |
| `MULTI_TENANT_DB_URL` | - | Multi-tenant database URL |
| `TENANT_PATHS` | `/api/v1` | Comma-separated paths for tenant context |
| `MULTI_TENANT_ENABLED` | `true` | Enable/disable plugin |

## Version

1.0.0 - Initial release

## License

MIT
