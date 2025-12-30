# AI4ICore Model Management Client

Reusable client library for integrating with the AI4ICore Model Management Service.

## Installation

```bash
pip install -e /path/to/ai4icore_model_management
```

## Usage

```python
from ai4icore_model_management import ModelManagementClient, extract_auth_headers

# Initialize client
client = ModelManagementClient(
    base_url="http://model-management-service:8091",
    cache_ttl_seconds=300
)

# Get service info
service_info = await client.get_service(
    service_id="my-service",
    auth_headers=extract_auth_headers(request)
)

# Use service info
endpoint = service_info.endpoint
model_name = service_info.triton_model
```

