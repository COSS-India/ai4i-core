# Monolith Inference Service - Architecture Summary

## ✅ Implementation Complete

All 7 steps have been completed. The monolith inference service now provides a unified endpoint for all inference task types.

---

## 📁 Directory Structure

```
/services/inference-service/
├── models/                              # Data models & schemas
│   ├── __init__.py
│   ├── common.py                        # GenericInferenceRequest/Response, ControlConfig
│   ├── task_types.py                    # TaskType enum, TaskRegistry
│   └── schemas/                         # Task-specific request/response models
│       ├── nmt.py
│       ├── asr.py
│       ├── ocr.py
│       ├── ner.py
│       ├── llm.py
│       ├── language_detection.py
│       ├── tts.py
│       ├── transliteration.py
│       ├── language_diarization.py
│       ├── speaker_diarization.py
│       ├── audio_language_detection.py
│       └── pii.py
│
├── orchestrator/                        # Orchestration layer
│   ├── __init__.py
│   └── orchestrator.py                  # Orchestrator with polymorphic routing
│
├── factory/                             # Service factory & registry
│   ├── __init__.py
│   └── task_factory.py                  # TaskFactory with DI
│
├── services/                            # Task-specific service implementations
│   ├── __init__.py
│   ├── nmt_service.py
│   ├── asr_service.py
│   ├── ocr_service.py
│   ├── ner_service.py
│   ├── llm_service.py
│   ├── language_detection_service.py
│   ├── tts_service.py
│   ├── transliteration_service.py
│   ├── language_diarization_service.py
│   ├── speaker_diarization_service.py
│   ├── audio_language_detection_service.py
│   └── pii_service.py
│
├── inference/                           # Inference server resolver
│   ├── __init__.py
│   └── inference_server_resolver.py     # Triton endpoint resolver with caching
│
├── inference-models/                    # Payload converters to/from Triton format
│   ├── __init__.py
│   ├── base_inference_model.py
│   ├── nmt_inference_model.py
│   ├── asr_inference_model.py
│   ├── ocr_inference_model.py
│   ├── ner_inference_model.py
│   ├── llm_inference_model.py
│   ├── tts_inference_model.py
│   ├── transliteration_inference_model.py
│   ├── language_diarization_inference_model.py
│   ├── speaker_diarization_inference_model.py
│   ├── audio_language_detection_inference_model.py
│   └── pii_inference_model.py
│
├── routes/                              # FastAPI routers & endpoints
│   ├── __init__.py
│   └── inference.py                     # POST /inference, GET /health, GET /tasks
│
├── utils/                               # Utility modules
│   ├── __init__.py
│   ├── telemetry.py                     # Structured span management
│   └── validation.py                    # Request validation & transformation
│
├── config.py                            # Settings from environment variables
├── app_factory.py                       # FastAPI app factory with DI setup
├── main.py                              # Entry point with Uvicorn
└── README.md, requirements.txt, etc.
```

---

## 🏗️ Architecture Components

### 1. **Models Layer** (`models/`)
- **`common.py`** — Generic request/response envelopes supporting polymorphic input arrays:
  - `GenericInferenceRequest` with `input`, `audio`, or `image` fields
  - `GenericInferenceResponse` with task-specific output
  - `ControlConfig` for optional control parameters

- **`task_types.py`** — Task registry mapping types to implementations:
  - `TaskType` enum (12 services)
  - `TaskRegistry` for registration & lookup

- **`schemas/`** — 12 task-specific Pydantic models:
  - Request models (e.g., `NMTInferenceRequest`)
  - Config models with discriminated unions (e.g., `NMTConfig`)
  - Response models (e.g., `NMTInferenceResponse`)

### 2. **Pipeline Base** (`services/base/task_service.py`)
- **`BaseTaskService`** — pipeline template all services inherit (Template Method):
  ```
  process():
      validate_request(payload)                      # throws on bad input
      preprocessed = preprocess_input(payload)
      result: PostProcessFormat = run_inference(preprocessed)
      return postprocess_output(result)
  ```
  - `run_inference()` — generic, the ONLY implementation (no overrides);
    call topology is data/class-driven (`adapter_config["call_mode"]` or
    `TRITON_CALL_MODE`: batch vs per-item). TTS expands items into chunks in
    preprocess_input and merges results in postprocess_output. Output
    conversion is adapter_config-driven via GenericTritonMapper, incl.
    transforms like `json_field` (Surya envelope unwrap)
  - `postprocess_output(result)` — post-inference only (audit/observability/
    model-specific final shaping); base default pairs sources + echoes config,
    which is the full contract for e.g. NMT
  - `payload_key` — modality input key (`input` / `audio` / `image`)
- Span handling lives in `trace/request_span.py` (`traced_inference`,
  `finalize_span`) — no tracing code in the service classes.

### 3. **Orchestration Layer** (`orchestrator/`)
- **`Orchestrator`** — Polymorphic request router:
  - `route_inference(payload)` — Entry point
  - Deserializes generic payload to task-specific request
  - Validates config structure
  - Delegates to `TaskFactory`
  - Handles errors & SMR routing
  - Serializes response

### 4. **Factory Layer** (`factory/`)
- **`TaskFactory`** — Dependency injection & service creation:
  - `create_service(task_type, **dependencies)` — Instantiates services
  - `register_service()` — Registers new task types
  - `list_available_services()` — Discovery endpoint
  - Service caching for performance

### 5. **Service Layer** (`services/`)
- **12 TaskService implementations** (classes without implementation):
  - `NMTTaskService` — Neural Machine Translation
  - `ASRTaskService` — Automatic Speech Recognition
  - `OCRTaskService` — Optical Character Recognition
  - `NERTaskService` — Named Entity Recognition
  - `LLMTaskService` — Large Language Models
  - `LanguageDetectionTaskService`
  - `TTSTaskService` — Text-to-Speech
  - `TransliterationTaskService`
  - `LanguageDiarizationTaskService`
  - `SpeakerDiarizationTaskService`
  - `AudioLanguageDetectionTaskService`
  - `PIITaskService` — PII Detection & Redaction

Each service handles:
  - Task-specific request validation
  - Input preprocessing (text normalization, audio resampling, image resizing)
  - Service/model resolution via `InferenceServerResolver`
  - Triton inference calls
  - Fallback retry logic
  - Output postprocessing

### 6. **Inference Resolution Layer** (`inference/`)
- **`InferenceServerResolver`** — Triton endpoint lookup with dual-layer caching:
  - In-memory cache (fast lookup, TTL expiry)
  - Redis cache (distributed sharing)
  - Database fallback if caches miss
  - Supports both required and SMR-optional `serviceId`
  - `resolve_service(service_id)` → `(model_name, triton_endpoint, api_key)`
  - `resolve_smr_service(payload)` → `service_id` via Smart Model Router

### 7. **Inference Model Layer** (`inference-models/`)
- **`InferenceModel<T>`** — Abstract payload converter:
  - `convert_payload_to_triton_format()` → `(triton_inputs, output_names)`
  - `convert_triton_output_to_task_format()` → task-specific output

- **12 task-specific converters**:
  - `NMTInferenceModel` — Handles language pair formatting
  - `ASRInferenceModel` — Audio decoding, resampling, chunking
  - `OCRInferenceModel` — Image normalization, layout extraction
  - `NERInferenceModel` — Tokenization, entity extraction from BIO labels
  - `LLMInferenceModel` — Prompt formatting, token counting
  - `TTSInferenceModel` — Audio synthesis, base64 encoding
  - And 6 more for other services...

### 8. **API Layer** (`routes/`)
- **`inference.py`** — FastAPI router with:
  - `POST /api/v1/inference` — Unified inference endpoint
  - `GET /api/v1/inference/health` — Health check
  - `GET /api/v1/inference/tasks` — List available tasks
  - `GET /api/v1/inference/tasks/{task_type}` — Task info & schema

### 9. **Utilities** (`utils/`)
- **`telemetry.py`** — OpenTelemetry integration:
  - `TelemetryContext` — Parent/child span management
  - `Span` — Individual operation tracing
  - Structured logging at each phase

- **`validation.py`** — Request/response validation:
  - `ValidationUtility` — Polymorphic input validation, schema checking
  - `PayloadTransformer` — Generic ↔ task-specific conversions

---

## 🔄 Data Flow

```
Client Request (JSON)
        ↓
POST /inference
        ↓
Orchestrator.route_inference(payload)
        ├─ Validate task_type is registered
        ├─ Deserialize to task-specific request model
        ├─ Validate config structure
        └─ Delegate to TaskFactory
                ↓
        TaskFactory.create_service(task_type, dependencies)
                ↓
        TaskService.process(payload, serviceInfo)
                ├─ validate_request
                ├─ preprocess_input (payload → preprocessed payload)
                ├─ run_inference → PostProcessFormat (inside ai-inference span)
                │   ├─ Convert payload to Triton format (GenericTritonMapper)
                │   ├─ Call Triton inference server
                │   └─ Convert Triton output to task format
                └─ postprocess_output (output shaping + envelope)
                └─ Postprocess output
                        ↓
        Response (JSON)
```

---

## 📋 Key Design Patterns

### 1. **Polymorphic Input Arrays**
- Text services use `input` key: `[{"source": "text"}, ...]`
- Audio services use `audio` key: `[{"audio_content": "base64", ...}, ...]`
- Image services use `image` key: `[{"image_content": "base64", ...}, ...]`
- Validated at envelope level, extracted by `GenericInferenceRequest.get_input_data()`

### 2. **Discriminated Union Configs**
- All configs extend task-specific model (e.g., `NMTConfig`, `ASRConfig`)
- Validated via `TaskRegistry.get_config_model(task_type)`
- No forcing services into wrong config patterns

### 3. **Dual-Layer Caching**
- **In-memory cache** — Fast TTL-based lookup
- **Redis cache** — Distributed sharing across instances
- **Database query** — Fallback if caches miss
- Reduces load on Model Management Service

### 4. **Service Routing Patterns**
- **Required serviceId** (OCR, NER, LLM, etc.) — Must be provided
- **Optional serviceId** (NMT, ASR, TTS) — Uses SMR if not provided
- Resolver handles both patterns transparently

### 5. **Structured Telemetry**
- Parent span for orchestration phase
- Child spans for each task phase:
  - `preprocess` — Input transformation
  - `resolve_model` — Service/model lookup
  - `triton_call` — Triton inference
  - `postprocess` — Output formatting
- Enables end-to-end tracing

### 6. **Error Handling with Fallback**
- Tasks implement fallback retry logic
- On primary service failure, try fallback service (if available)
- Errors bubble up to Orchestrator for HTTP response

---

## 🚀 Usage Example

### Request
```json
{
  "task_type": "NMT",
  "input": [
    {"source": "Hello, how are you?"}
  ],
  "config": {
    "service_id": "nmt-service-001",
    "language": {
      "source_language": "en",
      "target_language": "hi",
      "target_script_code": "Deva"
    }
  }
}
```

### Response
```json
{
  "output": [
    {
      "source": "Hello, how are you?",
      "target": "नमस्ते, आप कैसे हैं?"
    }
  ],
  "smr_response": null
}
```

---

## 🔧 Implementation Checklist

- ✅ Classes and methods created (no implementation)
- ✅ All 12 services included
- ✅ Polymorphic input arrays (input/audio/image) enforced at envelope
- ✅ Generic TaskConfig with discriminated unions
- ✅ Task registry for all 12 services
- ✅ Orchestrator with error handling
- ✅ TaskFactory with dependency injection
- ✅ InferenceServerResolver with dual-layer caching
- ✅ All 12 InferenceModel converters
- ✅ Unified /inference endpoint
- ✅ Health check & task discovery endpoints
- ✅ Telemetry context with structured spans
- ✅ Configuration via environment variables

---

## 📝 Next Steps for Implementation

1. **Service Implementation** — Add actual logic to `run_inference()` methods
2. **Payload Converters** — Implement Triton format conversion in InferenceModel classes
3. **Database Integration** — Connect InferenceServerResolver to actual DB
4. **Triton Client** — Implement Triton HTTP/gRPC calls
5. **Testing** — Unit & integration tests for each service
6. **Deployment** — Docker containerization, K8s manifests

---

## 📚 Files Count

- **56 Python files** created (all classes/methods, no implementation)
- **Models**: 15 files (common, task_types, 12 schemas)
- **Interfaces**: 1 file (task_service)
- **Orchestrator**: 1 file
- **Factory**: 1 file
- **Services**: 12 files
- **Inference**: 1 file (resolver)
- **Inference-models**: 13 files (base + 12 converters)
- **Routes**: 1 file
- **Utils**: 2 files (telemetry, validation)
- **Core**: 3 files (config, app_factory, main)

---

**All classes and methods are defined with proper signatures and docstrings, ready for implementation.**
