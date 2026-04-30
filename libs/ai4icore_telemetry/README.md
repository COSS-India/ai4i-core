# AI4ICore Telemetry Library

Distributed tracing and log aggregation for AI4ICore services.

## Features

- ✅ **Distributed Tracing**: OpenTelemetry integration with Jaeger
- ✅ **Log Storage**: OpenSearch client for log aggregation
- ✅ **Easy Integration**: Simple setup for FastAPI services

## Installation

```bash
cd libs/ai4icore_telemetry
pip install -e .
```

## Quick Start

### Tracing Setup

```python
from ai4icore_telemetry import setup_tracing

# In your service main.py
tracer = setup_tracing("ocr-service")
```

### OpenSearch Client

```python
from ai4icore_telemetry import get_opensearch_client, create_log_index

# Get client
client = get_opensearch_client()

# Create index
await create_log_index(client, "logs")
```

## Environment Variables

- `JAEGER_ENDPOINT`: Jaeger OTLP endpoint (default: `http://jaeger:4317`)
- `OPENSEARCH_URL`: OpenSearch URL (default: `http://opensearch:9200`)
- `OPENSEARCH_USERNAME`: OpenSearch username (default: `admin`)
- `OPENSEARCH_PASSWORD`: OpenSearch password (default: `admin`)
