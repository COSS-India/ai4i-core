# Triton Inference Server: Python Integration Guide

**Date**: April 30, 2026  
**Reference**: [NVIDIA Triton Architecture](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/architecture.html)  
**Scope**: Python ClientAPI, Model Management, Protocol Support

---

## Table of Contents

1. [Introduction](#introduction)
2. [Triton Architecture Overview](#triton-architecture-overview)
3. [Installation & Setup](#installation--setup)
4. [Client API Overview](#client-api-overview)
5. [Protocol Support](#protocol-support)
6. [Model Repository Structure](#model-repository-structure)
7. [Supported Model Backends](#supported-model-backends)
8. [Python Client Implementation](#python-client-implementation)
9. [Advanced Features](#advanced-features)
10. [Best Practices](#best-practices)
11. [Integration with Microservices](#integration-with-microservices)

---

## 1. Introduction

**Triton Inference Server** is a production-ready inference serving platform that:
- Supports multiple deep learning frameworks and model types
- Provides high-performance inference with batching and scheduling
- Offers flexible deployment options (cloud, on-premises, edge)
- Enables multi-model serving on a single server
- Provides comprehensive metrics and monitoring

### Key Use Cases
- Real-time inference serving
- Batch processing
- Multi-model pipelines
- Model ensemble serving
- Custom pre/post-processing

---

## 2. Triton Architecture Overview
![alt text](./images/triton-architecture.png)

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                      │
│                 (Python, Java, C++, etc.)                   │
└─────────┬────────────────────────┬───────────────────┬──────┘
          │                        │                   │
          ▼ HTTP/REST             ▼ gRPC             ▼ C API
┌─────────────────────────────────────────────────────────────┐
│              Triton Inference Server                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Request/Response Handler                    │   │
│  │  - Protocol Management (HTTP/gRPC/C API)             │   │
│  │  - Request Validation                                 │   │
│  │  - Load Balancing                                     │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│  ┌──────────────▼───────────────────────────────────────┐   │
│  │        Model Management & Scheduling                  │   │
│  │  - Model Registry                                     │   │
│  │  - Dynamic Model Loading/Unloading                    │   │
│  │  - Request Scheduling & Batching                      │   │
│  │  - Query & Control API                                │   │
│  └──────────────┬───────────────────────────────────────┘   │
│                 │                                            │
│         ┌───────┴──────────┬──────────────┬────────────┐     │
│         │                  │              │            │     │
│         ▼                  ▼              ▼            ▼     │
│  ┌────────────┐     ┌────────────┐  ┌────────────┐  ┌──────┐│
│  │ TensorFlow │     │   PyTorch  │  │    ONNX    │  │Custom││
│  │  Backend   │     │  Backend   │  │  Backend   │  │Backend││
│  └────────────┘     └────────────┘  └────────────┘  └──────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              GPU/CPU Execution Engine                 │   │
│  │  - CUDA/cuDNN (GPU)                                   │   │
│  │  - TensorRT (GPU Optimization)                        │   │
│  │  - OpenVINO (CPU)                                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Model Repository                               │
│  /models/                                                   │
│  ├── model_1/                                               │
│  │   ├── config.pbtxt                                       │
│  │   ├── 1/                                                 │
│  │   │   └── model.savedmodel/ or model.onnx                │
│  ├── model_2/                                               │
│  │   └── ...                                                │
│  └── ensemble_model/                                        │
│      └── config.pbtxt                                       │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Key Components

| Component | Purpose |
|-----------|---------|
| **HTTP/REST Interface** | Stateless request handling, easy integration, firewall-friendly |
| **gRPC Interface** | Low-latency, bidirectional streaming, protocol buffer serialization |
| **C API** | Direct in-process access, minimal overhead, custom applications |
| **Model Repository** | File-system storage of models with versioning |
| **Scheduler** | Manages request ordering, batching, priority |
| **Backend** | Framework-specific execution (TensorFlow, PyTorch, ONNX, etc.) |
| **Model Manager** | Dynamic model loading, versioning, health checks |

---

## 3. Installation & Setup

### 3.1 Server Installation

#### Option 1: Docker (Recommended)
```bash
# Pull official Triton image
docker pull nvcr.io/nvidia/tritonserver:24.02-py3

# Run with GPU
docker run --gpus all --rm -p8000:8000 -p8001:8001 -p8002:8002 \
  -v /path/to/model_repository:/models \
  nvcr.io/nvidia/tritonserver:24.02-py3 \
  tritonserver --model-repository=/models
```

#### Option 2: Install from Source
```bash
# Using Triton's NGC container
docker build -t triton-custom -f Dockerfile .

# Or native installation (advanced)
# Follow: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/build.html
```

### 3.2 Python Client Installation

```bash
# Install Triton Python client
pip install tritonclient[all]

# Breakdown:
# tritonclient[grpc]    - gRPC protocol support
# tritonclient[http]    - HTTP/REST protocol support
# tritonclient[all]     - All protocols
```

### 3.3 Verify Installation

```bash
# Check Triton server is running
curl -v http://localhost:8000/v2/health/ready

# Expected response: 200 OK

# Check available models
curl http://localhost:8000/v2/models
```

---

## 4. Client API Overview

### 4.1 Triton Python Client Architecture

```
┌──────────────────────────────────────────┐
│   Triton Python Client Library           │
├──────────────────────────────────────────┤
│                                          │
│  ┌──────────────┐   ┌───────────────┐   │
│  │   gRPC       │   │   HTTP/REST   │   │
│  │   Client     │   │   Client      │   │
│  └──────┬───────┘   └───────┬───────┘   │
│         │                   │           │
│  ┌──────▼───────────────────▼───────┐   │
│  │   Common Protocol Abstraction     │   │
│  │  - Request/Response Serialization │   │
│  │  - Data Type Conversion           │   │
│  │  - Error Handling                 │   │
│  └──────┬──────────────────────────┘   │
│         │                              │
│         ▼                              │
│  ┌─────────────────────────────────┐   │
│  │  Model Inference Interface      │   │
│  │  - infer()                      │   │
│  │  - stream_infer()               │   │
│  │  - get_model_config()           │   │
│  │  - get_model_metadata()         │   │
│  │  - get_server_metadata()        │   │
│  └─────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  Model Management Interface      │   │
│  │  - load_model()                  │   │
│  │  - unload_model()                │   │
│  │  - model_ready()                 │   │
│  │  - get_model_repository_index()  │   │
│  └──────────────────────────────────┘   │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │  Server Metadata Interface       │   │
│  │  - server_ready()                │   │
│  │  - server_live()                 │   │
│  │  - get_server_statistics()       │   │
│  └──────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

### 4.2 Client Classes

#### HTTP/REST Client
```python
import tritonclient.http as httpclient

# Initialize client
client = httpclient.InferenceServerClient(
    url="localhost:8000",
    verbose=False,
    insecure=False
)

# Key methods:
# - infer(model_name, inputs, outputs)
# - get_model_config(model_name)
# - get_model_metadata(model_name)
# - model_ready(model_name)
# - load_model(model_name)
# - unload_model(model_name)
```

#### gRPC Client
```python
import tritonclient.grpc as grpcclient

# Initialize client
client = grpcclient.InferenceServerClient(
    url="localhost:8001",
    verbose=False,
    ssl=False,
    root_certificates=None,
    private_key=None,
    certificate_chain=None
)

# Key methods (same as HTTP):
# - infer(model_name, inputs, outputs)
# - get_model_config(model_name)
# - async_infer()
# - stream_infer()
```

---

## 5. Protocol Support

### 5.1 HTTP/REST Protocol

```
┌─────────────────────────────────────────────────────┐
│ HTTP/REST Protocol Details                          │
├─────────────────────────────────────────────────────┤
│ Port: 8000                                          │
│ Endpoints:                                          │
│  - /v2/models/{model_name}                          │
│  - /v2/models/{model_name}/versions/{version}       │
│  - /v2/models/{model_name}/infer                    │
│  - /v2/models/{model_name}/versions/{v}/infer      │
│  - /v2/models                                       │
│  - /v2/health/ready                                 │
│  - /v2/health/live                                  │
│  - /v2/repository/index                             │
└─────────────────────────────────────────────────────┘
```

#### Features
- ✅ Firewall-friendly (standard HTTP)
- ✅ Easy debugging (human-readable JSON)
- ✅ Browser-testable
- ✅ Load-balancer compatible
- ❌ Higher latency
- ❌ More overhead

#### Example Request
```json
POST /v2/models/transliteration/infer
Content-Type: application/json

{
  "inputs": [
    {
      "name": "input_text",
      "shape": [1, 1],
      "datatype": "BYTES",
      "data": ["namaste"]
    }
  ],
  "outputs": [
    {
      "name": "output_text"
    }
  ]
}
```

### 5.2 gRPC Protocol

```
┌─────────────────────────────────────────────────────┐
│ gRPC Protocol Details                               │
├─────────────────────────────────────────────────────┤
│ Port: 8001                                          │
│ Protocol Buffers for serialization                  │
│ Features:                                           │
│  - Bidirectional streaming                          │
│  - Multiplexed over single TCP connection           │
│  - Binary format (smaller payload)                  │
│  - Lower latency                                    │
│  - Async support                                    │
└─────────────────────────────────────────────────────┘
```

#### Features
- ✅ Lower latency
- ✅ Binary protocol (smaller payload)
- ✅ Bidirectional streaming
- ✅ Async support
- ✅ Better for high-frequency requests
- ❌ Requires protocol buffer knowledge
- ❌ Less browser-testable

### 5.3 C API

```
┌─────────────────────────────────────────────────────┐
│ C API Protocol                                      │
├─────────────────────────────────────────────────────┤
│ In-process linking                                  │
│ Port: None (in-memory)                              │
│ Use Cases:                                          │
│  - Minimal latency                                  │
│  - Custom C/C++ applications                        │
│  - Embedded systems                                 │
│  - Java/Python via ctypes/JNI                       │
└─────────────────────────────────────────────────────┘
```

---

## 6. Model Repository Structure

### 6.1 Repository Layout

```
model_repository/
├── model_1/
│   ├── config.pbtxt                 # Model configuration
│   ├── 1/                           # Version 1 (default)
│   │   ├── model.savedmodel/        # TensorFlow SavedModel
│   │   │   ├── saved_model.pb
│   │   │   └── variables/
│   │   │       └── variables.data-00000-of-00001
│   │   ├── model.onnx               # ONNX model
│   │   └── model.pt                 # PyTorch model
│   └── 2/                           # Version 2
│       └── model.savedmodel/
│
├── model_2/
│   ├── config.pbtxt
│   ├── 1/
│   │   └── model.onnx
│   └── 2/
│       └── model.onnx
│
└── ensemble_model/
    ├── config.pbtxt                 # Ensemble config
    └── 1/                           # No model directory for ensemble
```

### 6.2 Model Configuration (config.pbtxt)

```protobuf
# TensorFlow Model Example
name: "transliteration"
platform: "tensorflow_savedmodel"
max_batch_size: 256

input [
  {
    name: "input_text"
    data_type: TYPE_STRING
    dims: [-1]
  }
]

output [
  {
    name: "output_text"
    data_type: TYPE_STRING
    dims: [-1]
  },
  {
    name: "scores"
    data_type: TYPE_FP32
    dims: [-1]
  }
]

instance_group [
  {
    kind: KIND_GPU
    gpus: [0]
  }
]
```

### 6.3 Configuration Options

| Option | Purpose |
|--------|---------|
| `name` | Model identifier |
| `platform` | Backend type (tensorflow_savedmodel, onnx_runtime, pytorch_libtorch) |
| `max_batch_size` | Maximum batch size for dynamic batching |
| `input/output` | Tensor specifications (name, datatype, shape) |
| `instance_group` | GPU/CPU allocation |
| `dynamic_batching` | Batching strategy configuration |
| `version_policy` | Model versioning strategy |
| `ensemble_scheduling` | For ensemble models |

---

## 7. Supported Model Backends

### 7.1 Backend Comparison

| Backend | Frameworks | Use Case | Performance |
|---------|-----------|----------|-------------|
| **TensorFlow SavedModel** | TF 1.x, 2.x | Broad ecosystem | Good |
| **ONNX Runtime** | PyTorch, TF, Scikit-learn, XGBoost | Framework agnostic | Excellent |
| **PyTorch LibTorch** | PyTorch | PyTorch models | Excellent |
| **TensorRT** | NVIDIA Optimized | GPU optimization | Outstanding |
| **OpenVINO** | Intel models | CPU optimization | Very Good |
| **Python Backend** | Any Python code | Custom logic | Good |
| **Custom Backend** | Any framework | Specialized needs | Variable |

### 7.2 Backend-Specific Configuration

#### TensorFlow SavedModel
```protobuf
name: "tf_model"
platform: "tensorflow_savedmodel"
version_policy: { latest { num_versions: 3 } }
dynamic_batching {
  preferred_batch_size: [64]
  max_queue_delay_microseconds: 100
}
```

#### ONNX Runtime
```protobuf
name: "onnx_model"
platform: "onnxruntime_onnx"
dynamic_batching {
  preferred_batch_size: [32, 64]
}
```

#### PyTorch LibTorch
```protobuf
name: "pytorch_model"
platform: "pytorch_libtorch"
instance_group [{
  kind: KIND_GPU
  count: 1
}]
```

#### Python Backend (Custom Code)
```protobuf
name: "python_model"
platform: "python"
backend: "python"
instance_group [{
  kind: KIND_GPU
  count: 1
}]
```

---

## 8. Python Client Implementation

### 8.1 Basic Inference - HTTP

```python
import tritonclient.http as httpclient
import numpy as np

# Initialize client
client = httpclient.InferenceServerClient(url="localhost:8000")

# Check server health
print("Server ready:", client.is_server_ready())

# Get model info
model_metadata = client.get_model_metadata(model_name="transliteration")
print(f"Model inputs: {model_metadata['inputs']}")
print(f"Model outputs: {model_metadata['outputs']}")

# Prepare inputs
input_text = "namaste"
inputs = [
    httpclient.InferInput(
        "input_text",
        [1],
        "BYTES"
    )
]
inputs[0].set_data_from_numpy(np.array([input_text], dtype=object))

# Prepare outputs
outputs = [
    httpclient.InferRequestedOutput("output_text"),
    httpclient.InferRequestedOutput("scores")
]

# Execute inference
response = client.infer(
    model_name="transliteration",
    inputs=inputs,
    outputs=outputs
)

# Get results
output_text = response.as_numpy("output_text")
scores = response.as_numpy("scores")

print(f"Transliterated: {output_text[0]}")
print(f"Scores: {scores[0]}")
```

### 8.2 Batch Inference - HTTP

```python
import tritonclient.http as httpclient
import numpy as np

client = httpclient.InferenceServerClient(url="localhost:8000")

# Batch input
texts = ["namaste", "shukriya", "hello"]
batch_size = len(texts)

inputs = [
    httpclient.InferInput(
        "input_text",
        [batch_size],
        "BYTES"
    )
]
inputs[0].set_data_from_numpy(np.array(texts, dtype=object))

outputs = [
    httpclient.InferRequestedOutput("output_text"),
    httpclient.InferRequestedOutput("scores")
]

# Single call for entire batch
response = client.infer(
    model_name="transliteration",
    inputs=inputs,
    outputs=outputs
)

output_texts = response.as_numpy("output_text")
scores = response.as_numpy("scores")

for i, text in enumerate(texts):
    print(f"{text} -> {output_texts[i]} (score: {scores[i][0]})")
```

### 8.3 Async Inference - gRPC

```python
import tritonclient.grpc as grpcclient
import numpy as np
import asyncio

async def async_infer():
    # Initialize async client
    client = grpcclient.InferenceServerClient(url="localhost:8001")
    
    # Prepare inputs
    input_text = "namaste"
    inputs = [
        grpcclient.InferInput("input_text", [1], "BYTES")
    ]
    inputs[0].set_data_from_numpy(np.array([input_text], dtype=object))
    
    outputs = [
        grpcclient.InferRequestedOutput("output_text"),
        grpcclient.InferRequestedOutput("scores")
    ]
    
    # Async inference
    response = await client.async_infer(
        model_name="transliteration",
        inputs=inputs,
        outputs=outputs
    )
    
    output_text = response.as_numpy("output_text")
    scores = response.as_numpy("scores")
    
    return output_text[0], scores[0]

# Run async inference
result = asyncio.run(async_infer())
print(result)
```

### 8.4 Streaming Inference - gRPC

```python
import tritonclient.grpc as grpcclient
import numpy as np

def streaming_infer():
    client = grpcclient.InferenceServerClient(url="localhost:8001")
    
    texts = ["namaste", "shukriya", "hello", "thank you"]
    
    # Generator for streaming requests
    def requests_generator():
        for text in texts:
            inputs = [
                grpcclient.InferInput("input_text", [1], "BYTES")
            ]
            inputs[0].set_data_from_numpy(np.array([text], dtype=object))
            
            outputs = [
                grpcclient.InferRequestedOutput("output_text"),
                grpcclient.InferRequestedOutput("scores")
            ]
            
            yield grpcclient.InferRequest(
                model_name="transliteration",
                inputs=inputs,
                outputs=outputs,
                request_id="request_" + str(texts.index(text))
            )
    
    # Stream results
    responses = client.stream_infer(requests_generator=requests_generator())
    
    for response in responses:
        output_text = response.as_numpy("output_text")
        print(f"Streamed result: {output_text[0]}")

streaming_infer()
```

### 8.5 Model Management - HTTP

```python
import tritonclient.http as httpclient

client = httpclient.InferenceServerClient(url="localhost:8000")

# Load a model
try:
    client.load_model("transliteration")
    print("Model loaded successfully")
except Exception as e:
    print(f"Load failed: {e}")

# Check model readiness
is_ready = client.is_model_ready("transliteration")
print(f"Model ready: {is_ready}")

# Get model configuration
config = client.get_model_config("transliteration")
print(f"Model config: {config}")

# Get model metadata
metadata = client.get_model_metadata("transliteration")
print(f"Model metadata: {metadata}")

# List all models
models = client.get_model_repository_index()
print(f"Available models: {models}")

# Unload model
try:
    client.unload_model("transliteration")
    print("Model unloaded successfully")
except Exception as e:
    print(f"Unload failed: {e}")
```

### 8.6 Server Statistics - gRPC

```python
import tritonclient.grpc as grpcclient

client = grpcclient.InferenceServerClient(url="localhost:8001")

# Server metadata
server_metadata = client.get_server_metadata()
print(f"Server name: {server_metadata.name}")
print(f"Version: {server_metadata.version}")

# Model statistics
model_stats = client.get_model_statistics("transliteration")
print(f"Inference count: {model_stats.model_stats}")
```

### 8.7 Error Handling

```python
import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

client = httpclient.InferenceServerClient(url="localhost:8000")

try:
    # Attempt inference
    response = client.infer(
        model_name="transliteration",
        inputs=inputs,
        outputs=outputs
    )
    
except InferenceServerException as e:
    # Handle Triton-specific errors
    print(f"Inference error: {e}")
    
    # Error types:
    # - ModelNotFound: Model doesn't exist
    # - ModelUnavailable: Model not loaded/ready
    # - InvalidModelVersion: Version doesn't exist
    # - InvalidRequest: Input/output mismatch
    # - Unavailable: Server not ready
    
except ConnectionError as e:
    print(f"Connection error: {e}")
    
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## 9. Advanced Features

### 9.1 Dynamic Batching

```protobuf
# Model config with dynamic batching
name: "transliteration"
platform: "tensorflow_savedmodel"
max_batch_size: 256

dynamic_batching {
  # Preferred batch sizes
  preferred_batch_size: [64, 128]
  
  # Max wait time before executing partial batch (microseconds)
  max_queue_delay_microseconds: 100
  
  # Priority levels
  priority_levels: 2
  
  # Default priority
  default_queue_policy {
    timeout_action: DECREMENT
    timeout_ms: 1000
    default_priority_level: 0
  }
}
```

### 9.2 Ensemble Models

```protobuf
# Ensemble model configuration
name: "nlp_pipeline"
platform: "ensemble"
max_batch_size: 128

ensemble_scheduling {
  # Step 1: Transliteration
  step {
    model_name: "transliteration"
    model_version: -1
    input_map {
      key: "input_text"
      value: "INPUT_TEXT"
    }
    output_map {
      key: "output_text"
      value: "XLIT_OUTPUT"
    }
  }
  
  # Step 2: NER (using transliteration output)
  step {
    model_name: "ner"
    model_version: -1
    input_map {
      key: "input_text"
      value: "XLIT_OUTPUT"
    }
    output_map {
      key: "entities"
      value: "FINAL_ENTITIES"
    }
  }
}

input {
  name: "INPUT_TEXT"
  data_type: TYPE_STRING
  dims: [-1]
}

output {
  name: "FINAL_ENTITIES"
  data_type: TYPE_STRING
  dims: [-1]
}
```

#### Python Client for Ensemble

```python
import tritonclient.http as httpclient
import numpy as np

client = httpclient.InferenceServerClient(url="localhost:8000")

# Call ensemble (which internally calls transliteration + NER)
inputs = [
    httpclient.InferInput("INPUT_TEXT", [1], "BYTES")
]
inputs[0].set_data_from_numpy(np.array(["namaste"], dtype=object))

outputs = [
    httpclient.InferRequestedOutput("FINAL_ENTITIES")
]

response = client.infer(
    model_name="nlp_pipeline",  # Ensemble model name
    inputs=inputs,
    outputs=outputs
)

entities = response.as_numpy("FINAL_ENTITIES")
print(f"Entities: {entities[0]}")
```

### 9.3 Model Versioning

```python
import tritonclient.http as httpclient
import numpy as np

client = httpclient.InferenceServerClient(url="localhost:8000")

# Infer with specific version
response = client.infer(
    model_name="transliteration",
    model_version="2",  # Use version 2
    inputs=inputs,
    outputs=outputs
)

# Get specific version config
config_v1 = client.get_model_config("transliteration", "1")
config_v2 = client.get_model_config("transliteration", "2")

# Get specific version metadata
metadata_v2 = client.get_model_metadata("transliteration", "2")
```

### 9.4 Request Priority

```protobuf
# Model config with priorities
name: "transliteration"
platform: "tensorflow_savedmodel"
max_batch_size: 256

# Enable 2 priority levels
priority_levels: 2

dynamic_batching {
  preferred_batch_size: [64]
  max_queue_delay_microseconds: 100
  
  priority_queue_policy {
    # High priority (level 0) - shorter timeout
    {
      timeout_action: DECREMENT
      timeout_ms: 100
      default_priority_level: 0
    }
    # Low priority (level 1) - longer timeout
    {
      timeout_action: DECREMENT
      timeout_ms: 500
      default_priority_level: 1
    }
  }
}
```

#### Python Client with Priority

```python
import tritonclient.http as httpclient

client = httpclient.InferenceServerClient(url="localhost:8000")

# High priority request (priority = 0)
response = client.infer(
    model_name="transliteration",
    inputs=inputs,
    outputs=outputs,
    request_id="urgent_request",
    headers={"priority": "0"}  # 0 = highest priority
)

# Low priority request (priority = 1)
response = client.infer(
    model_name="transliteration",
    inputs=inputs,
    outputs=outputs,
    request_id="background_request",
    headers={"priority": "1"}  # 1 = lower priority
)
```

### 9.5 Custom Metrics & Monitoring

```python
import tritonclient.http as httpclient
from prometheus_client import Counter, Histogram, start_http_server
import time

# Setup Prometheus metrics
inference_counter = Counter('triton_inferences_total', 'Total inferences', ['model', 'status'])
inference_latency = Histogram('triton_inference_latency_seconds', 'Inference latency', ['model'])

# Start metrics server
start_http_server(8888)

client = httpclient.InferenceServerClient(url="localhost:8000")

# Inference with metrics
start_time = time.time()
try:
    response = client.infer(
        model_name="transliteration",
        inputs=inputs,
        outputs=outputs
    )
    inference_counter.labels(model="transliteration", status="success").inc()
except Exception as e:
    inference_counter.labels(model="transliteration", status="error").inc()
    raise
finally:
    latency = time.time() - start_time
    inference_latency.labels(model="transliteration").observe(latency)
    print(f"Latency: {latency*1000:.2f}ms")
```

---

## 10. Best Practices

### 10.1 Client Best Practices

```python
# ✅ Good: Connection pooling, error handling
class TritonClientManager:
    def __init__(self, url="localhost:8000"):
        self.client = None
        self.url = url
    
    def connect(self):
        if self.client is None:
            import tritonclient.http as httpclient
            self.client = httpclient.InferenceServerClient(url=self.url)
        return self.client
    
    def infer_with_retry(self, model, inputs, outputs, max_retries=3):
        for attempt in range(max_retries):
            try:
                client = self.connect()
                response = client.infer(model, inputs=inputs, outputs=outputs)
                return response
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
    
    def close(self):
        self.client = None

# Usage
manager = TritonClientManager()
response = manager.infer_with_retry("transliteration", inputs, outputs)
```

### 10.2 Data Type Handling

```python
import numpy as np
import tritonclient.http as httpclient

client = httpclient.InferenceServerClient(url="localhost:8000")

# String input
string_input = httpclient.InferInput("text", [1], "BYTES")
string_input.set_data_from_numpy(np.array(["hello"], dtype=object))

# Numeric input
numeric_input = httpclient.InferInput("values", [1, 3], "FP32")
numeric_input.set_data_from_numpy(np.array([[1.0, 2.0, 3.0]], dtype=np.float32))

# Integer input
int_input = httpclient.InferInput("ids", [1, 5], "INT64")
int_input.set_data_from_numpy(np.array([[1, 2, 3, 4, 5]], dtype=np.int64))

# Boolean input
bool_input = httpclient.InferInput("flags", [1, 2], "BOOL")
bool_input.set_data_from_numpy(np.array([[True, False]], dtype=bool))
```

### 10.3 Batch Size Optimization

```python
# Rule of thumb for batch sizes:
# GPU: 32, 64, 128 (powers of 2 preferred)
# CPU: 8, 16, 32 (smaller batches)
# Latency-sensitive: 1-16
# Throughput-sensitive: 64-256

# Adaptive batching based on load
import queue
import threading

class AdaptiveBatcher:
    def __init__(self, min_batch=1, max_batch=128, timeout_ms=100):
        self.queue = queue.Queue()
        self.min_batch = min_batch
        self.max_batch = max_batch
        self.timeout_ms = timeout_ms
    
    def batch_request(self, request_data):
        self.queue.put(request_data)
        
        # Collect batch
        batch = []
        try:
            while len(batch) < self.max_batch:
                item = self.queue.get(timeout=self.timeout_ms/1000.0)
                batch.append(item)
                if len(batch) >= self.min_batch:
                    break
        except queue.Empty:
            pass
        
        return batch
```

### 10.4 Model Configuration Best Practices

```protobuf
# ✅ Good model configuration
name: "transliteration"
platform: "tensorflow_savedmodel"

# Reasonable batch size
max_batch_size: 128

# Define clear I/O
input {
  name: "input_text"
  data_type: TYPE_STRING
  dims: [-1]
}

output {
  name: "output_text"
  data_type: TYPE_STRING
  dims: [-1]
}

# Dynamic batching for throughput
dynamic_batching {
  preferred_batch_size: [64]
  max_queue_delay_microseconds: 100
}

# GPU instance allocation
instance_group {
  kind: KIND_GPU
  count: 1
}

# Version policy
version_policy {
  latest {
    num_versions: 2
  }
}
```

### 10.5 Logging & Debugging

```python
import logging
import tritonclient.http as httpclient

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Verbose client
client = httpclient.InferenceServerClient(
    url="localhost:8000",
    verbose=True  # Prints HTTP requests/responses
)

# Custom logging wrapper
class LoggingTritonClient:
    def __init__(self, url):
        self.client = httpclient.InferenceServerClient(url=url)
        self.logger = logging.getLogger(__name__)
    
    def infer(self, model_name, inputs, outputs):
        self.logger.info(f"Calling model: {model_name}")
        self.logger.debug(f"Inputs: {inputs}")
        
        try:
            response = self.client.infer(model_name, inputs, outputs)
            self.logger.info(f"Inference successful")
            return response
        except Exception as e:
            self.logger.error(f"Inference failed: {e}")
            raise
```

---

## 11. Integration with Microservices

### 11.1 Single-Service Integration

```python
# app/services/transliteration_service_impl.py
from app.services.base_service import InferenceService
from app.services.triton_client import TritonClient
import tritonclient.http as httpclient
import numpy as np

class TransliterationServiceImpl(InferenceService):
    def __init__(self):
        self.triton_client = TritonClient()
    
    async def preProcess(self, input_data):
        """Validate and prepare input for Triton."""
        text = input_data.get("text", "")
        if not text:
            raise ValueError("Text is required")
        
        return {
            "input_text": text,
            "source_lang": input_data.get("source_lang", "hi"),
            "target_lang": input_data.get("target_lang", "en"),
        }
    
    async def postProcess(self, triton_output):
        """Format Triton response."""
        return {
            "transliterated_text": triton_output.get("output_text", ""),
            "confidence": triton_output.get("confidence", 0.0),
        }
    
    async def processData(self, request_data):
        """Full pipeline: preprocess → Triton → postprocess."""
        # Preprocess
        preprocessed = await self.preProcess(request_data)
        
        # Prepare Triton inputs
        inputs = [
            httpclient.InferInput("input_text", [1], "BYTES")
        ]
        inputs[0].set_data_from_numpy(
            np.array([preprocessed["input_text"]], dtype=object)
        )
        
        outputs = [
            httpclient.InferRequestedOutput("output_text"),
            httpclient.InferRequestedOutput("confidence"),
        ]
        
        # Execute Triton inference
        response = await self.triton_client.execute(
            model_name="transliteration",
            inputs=inputs,
            outputs=outputs
        )
        
        # Postprocess
        triton_output = {
            "output_text": response.as_numpy("output_text")[0],
            "confidence": response.as_numpy("confidence")[0],
        }
        
        return await self.postProcess(triton_output)
```

### 11.2 Multi-Protocol Support

```python
# app/services/triton_client.py
import tritonclient.http as httpclient
import tritonclient.grpc as grpcclient
import os

class TritonClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        self.protocol = os.getenv("TRITON_PROTOCOL", "http")
        self.url = os.getenv("TRITON_URL", "localhost:8000")
        
        if self.protocol == "http":
            self.client = httpclient.InferenceServerClient(url=self.url)
        elif self.protocol == "grpc":
            self.client = grpcclient.InferenceServerClient(url=self.url)
    
    async def execute(self, model_name, inputs, outputs):
        if self.protocol == "http":
            return self.client.infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs
            )
        elif self.protocol == "grpc":
            return await self.client.async_infer(
                model_name=model_name,
                inputs=inputs,
                outputs=outputs
            )
```

### 11.3 Model Registry & Discovery

```python
# app/orchestrator/model_registry.py
import tritonclient.http as httpclient

class ModelRegistry:
    def __init__(self, triton_url="localhost:8000"):
        self.client = httpclient.InferenceServerClient(url=triton_url)
    
    def get_available_models(self):
        """List all available models in Triton."""
        try:
            index = self.client.get_model_repository_index()
            return index
        except Exception as e:
            raise RuntimeError(f"Failed to fetch model index: {e}")
    
    def is_model_ready(self, model_name):
        """Check if model is ready for inference."""
        return self.client.is_model_ready(model_name)
    
    def get_model_info(self, model_name):
        """Get detailed model information."""
        return {
            "metadata": self.client.get_model_metadata(model_name),
            "config": self.client.get_model_config(model_name),
            "ready": self.client.is_model_ready(model_name),
        }
    
    def load_model(self, model_name):
        """Load a model dynamically."""
        self.client.load_model(model_name)
    
    def unload_model(self, model_name):
        """Unload a model."""
        self.client.unload_model(model_name)
```

### 11.4 Performance Monitoring

```python
# app/monitoring/triton_metrics.py
from prometheus_client import Counter, Histogram, Gauge
import time

class TritonMetrics:
    def __init__(self):
        self.inference_counter = Counter(
            'triton_inferences_total',
            'Total inferences',
            ['model', 'status']
        )
        
        self.inference_latency = Histogram(
            'triton_inference_latency_seconds',
            'Inference latency',
            ['model'],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
        )
        
        self.inference_batch_size = Histogram(
            'triton_inference_batch_size',
            'Inference batch size',
            ['model']
        )
        
        self.triton_queue_depth = Gauge(
            'triton_queue_depth',
            'Triton queue depth',
            ['model']
        )
    
    def record_inference(self, model_name, latency_ms, batch_size, status="success"):
        self.inference_counter.labels(model=model_name, status=status).inc()
        self.inference_latency.labels(model=model_name).observe(latency_ms/1000.0)
        self.inference_batch_size.labels(model=model_name).observe(batch_size)
```

---

## 12. Troubleshooting Guide

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| **ModelNotFound** | Model not in repository | Check model name, verify model repository path |
| **ModelUnavailable** | Model not loaded | `client.load_model()` or check server logs |
| **InvalidRequest** | Input shape/type mismatch | Verify input shape and datatype match config.pbtxt |
| **OutOfMemory** | GPU memory exceeded | Reduce batch size, check max_batch_size |
| **Timeout** | Request too slow | Check model performance, increase timeout |
| **Connection Refused** | Server not running | Start Triton: `docker run tritonserver` |
| **Port Already in Use** | Port conflict | Use different ports or check existing process |

---

## 13. Performance Tips

### Optimization Checklist

- [ ] Use gRPC for latency-critical applications
- [ ] Enable dynamic batching with `preferred_batch_size`
- [ ] Use TensorRT backend for NVIDIA GPUs
- [ ] Set appropriate `max_queue_delay_microseconds`
- [ ] Monitor GPU memory usage
- [ ] Use model versioning for A/B testing
- [ ] Enable request priority for SLAs
- [ ] Implement connection pooling
- [ ] Profile with multiple batch sizes
- [ ] Use Prometheus metrics for monitoring

---

**Document Version**: 1.0  
**Last Updated**: April 30, 2026  
**Maintainer**: AI4I Core Team
