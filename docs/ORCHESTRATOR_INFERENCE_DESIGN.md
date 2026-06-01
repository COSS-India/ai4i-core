# Multi-Service Inference Orchestrator Design

**Date**: June 1, 2026  
**Status**: Implemented  
**Target Services**: All micro-services with `/inference` endpoint calling Triton server  
**Design Patterns**: Strategy Pattern + Registry Pattern + Singleton Pattern

---

## 1. Executive Summary

This document proposes a unified, scalable architecture for handling inference requests across multiple micro-services. The design decouples service-specific logic from the orchestration layer, enabling:

- **Horizontal scalability**: Add new services without modifying orchestrator
- **Separation of concerns**: Each service handles its own preprocessing and postprocessing
- **Shared resources**: Singleton inference client across all services
- **Unified base execution**: `BaseTaskService` uses a common `TritonService` for `TextBase`, `AudioBase`, and `ImageBase` task types
- **Configuration-driven execution**: Chain multiple services dynamically
- **Testability**: Easy mocking and unit testing of individual components

---

## 2. Current Architecture Issues

### Problem Statement
Currently, each service implements its own `/inference` endpoint with redundant logic:
- Separate inference client initialization per service
- Duplicated request validation and error handling
- Service-specific processing scattered across multiple files
- No clear pattern for chaining multiple services
- Difficult to maintain consistency across services

---

## 3. Proposed Architecture

### 3.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│                  /api/v1/{service}/inference                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Inference Endpoint (FastAPI Router)            │
│              - Request Validation                           │
│              - Auth & Tenant Checks                         │
│              - Call Orchestrator                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Inference Orchestrator (Main Coordinator)          │
│  - Route request to the correct service class via registry  │
│  - Manage service chaining (if configured)                  │
│  - Aggregate results                                        │
│  - Handle errors & logging                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│        Task Service Registry (Configuration)                │
│  - Maps (task_type, model_name) to a service class          │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │  Trans. │    │   NMT   │    │   NER   │
    │ Service │    │ Service │    │ Service │
    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │
    (TextBase / AudioBase / ImageBase task services)
    (all inherit from BaseTaskService)
    - run_inference()
    - preprocess_input()
    - postprocess_output()
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│      BaseTaskService (Handles Generic Triton Interaction)   │
│  - Persistent connection to Triton server via HTTP client   │
│  - execute_triton_inference(payload) -> output              │
│  - Shared TritonService used by all task base families       │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              Triton Inference Server                         │
│              (Docker Container / Remote Host)               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Component Hierarchy

```
Core Abstractions
├── BaseTaskService (Abstract Base Class)
│   ├── process(payload) → BaseModel
│   ├── validate_request(payload) → None
│   ├── preprocess_input(input_data) → List[Dict]
│   ├── run_inference(payload) → Any
│   └── execute_triton_inference(payload) → Dict
│
├── Task Base Families
│   ├── TextBaseTaskService(BaseTaskService)
│   ├── AudioBaseTaskService(BaseTaskService)
│   └── ImageBaseTaskService(BaseTaskService)
│
├── TritonService (Shared Client)
│   └── Used by BaseTaskService for all task types
│
├── TaskServiceRegistry (Registry Pattern)
│   └── Maps (task_type, model_name) → service_class
│
└── InferenceOrchestrator (Coordinator)
    └── process_request(payload) → BaseModel

Service Implementations
├── TransliterationTaskService(TextBaseTaskService)
├── ASRTaskService(AudioBaseTaskService)
├── OCRTaskService(ImageBaseTaskService)
└── [Other services...]

Endpoints
└── FastAPI Router
    └── POST /inference → uses InferenceOrchestrator
```

---

## 4. Data Flow Diagrams

### 4.1 Single Service Execution Flow (with Smart Model Selection)

```
┌─────────────────────────────────────────────────┐
│   HTTP Request                                  │
│   {                                             │
│     service_id: "transliteration",              │
│     model_id: null  (or explicit model),        │
│     data: {...},                                │
│     config: { task_params: {...} }              │
│   }                                             │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  FastAPI Endpoint (/inference)                  │
│  ✓ Request validation                           │
│  ✓ Auth check & Tenant check                    │
│  ✓ Extract user context                         │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  InferenceOrchestrator.execute()                │
│  ✓ Extract task_type, model_name from request   │
│  ✓ Resolve service via TaskServiceRegistry      │
│  ✓ Instantiate service with service_info        │
└────────┬────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  TaskServiceRegistry lookup                      │
│  ✓ Match (task_type, model_name)                │
│  ✓ Return mapped service_class                  │
│  ✓ Construct BaseTaskService-derived instance   │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│ TaskService.process()                            │
│ ✓ validate -> preprocess -> run_inference       │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  getModel(model_id) - Smart Model Selection     │
│  ┌─────────────────────────────────────────┐    │
│  │ Decision Logic (3-level fallback):      │    │
│  │ 1. If model_id provided:                │    │
│  │    - Validate model                     │    │
│  │    - Return explicit model              │    │
│  │                                         │    │
│  │ 2. If model_id is None:                 │    │
│  │    - Use default model for service      │    │
│  └─────────────────────────────────────────┘    │
│  Output: selected_model_name                    │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  preProcess(input_data)                         │
│  ✓ Validate input                               │
│  ✓ Convert to Triton format                     │
│  Output: {input_text, language, ...}            │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  BaseTaskService.execute_triton_inference()     │
│  ✓ Uses shared TritonService client             │
│  ✓ Converts payload and calls Triton endpoint   │
│  ✓ Returns normalized task response data        │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  Triton Response                                │
│  {                                              │
│    "output": "nmst",                            │
│    "scores": [0.95, 0.89],                      │
│    "latency_ms": 12                             │
│  }                                              │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  postProcess(triton_output)                     │
│  ✓ Format output for response                   │
│  Output: {transliterated_text, confidence, ...} │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  Include Model Metadata in Response             │
│  {                                              │
│    "output": {...},                             │
│    "model_used": "transliteration-v2-fast",     │
│    "requested_model": null,                     │
│    "routing_strategy": "smart"                  │
│  }                                              │
└────────┬─────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────┐
│  HTTP Response (200 OK)                         │
│  {                                              │
│    "results": {                                 │
│      "transliteration": {                       │
│        "transliterated_text": "nmst",           │
│        "model_used": "v2-fast",                 │
│        "routing_strategy": "smart"              │
│      }                                          │
│    },                                           │
│    "user_id": "user123",                        │
│    "session_id": "sess456"                      │
│  }                                              │
└──────────────────────────────────────────────────┘
```

### 4.2 Multi-Service Chaining Flow

```
┌──────────────────────────────────────────┐
│   HTTP Request (Multi-Service Config)    │
│   {                                      │
│     data: {...},                         │
│     config: {                            │
│       services: [                        │
│         "transliteration",               │
│         "language-detection",            │
│         "ner"                            │
│       ]                                  │
│     }                                    │
│   }                                      │
└────────┬─────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│   InferenceOrchestrator.execute()          │
│   ✓ Parse config.services list             │
│   ✓ Initialize results dictionary          │
└────────┬───────────────────────────────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    │ Service │ Service  │ Service  │
    │    1    │    2     │    3     │
    │ "xlit"  │ "langdet"│  "ner"   │
    ▼         ▼          ▼
┌──────────────────────────────────────────┐
│  For each service in config.services:    │
│  1. Resolve service_class from registry  │
│  2. Call service.process()               │
│  3. Store result in results dict         │
│  4. Handle exceptions (log & continue)   │
└────────┬───────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│  Aggregated Results                        │
│  {                                         │
│    "results": {                            │
│      "transliteration": {...},             │
│      "language_detection": {...},          │
│      "ner": {...}                          │
│    },                                      │
│    "user_id": "user123",                   │
│    "session_id": "sess456"                 │
│  }                                         │
└────────┬───────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────┐
│  HTTP Response (200 OK)                    │
└────────────────────────────────────────────┘
```

---

## 5. Component Specifications

### 5.1 BaseTaskService and Task Base Families

- `BaseTaskService` is the common execution layer for all task services.
- `TextBase`, `AudioBase`, and `ImageBase` families inherit from `BaseTaskService`.
- Common pipeline behavior is centralized: request validation, preprocessing, Triton execution, and response postprocessing.

### 5.2 TritonService (Shared Across BaseTaskService)

- `TritonService` is shared by all task base families.
- No task type owns a separate Triton client implementation.
- `BaseTaskService` delegates server communication to `TritonService`.

### 5.3 TaskServiceRegistry

- Registry-driven mapping: `(task_type, model_name) -> service_class`.
- New task/model onboarding only requires registry updates and service implementation.
- No task factory layer is used.

### 5.4 InferenceOrchestrator

- Orchestrator resolves service classes from `TaskServiceRegistry`.
- For each request (or pipeline step), it instantiates the mapped service with resolved `service_info`.
- It executes `process()` and aggregates outputs.

---

## 6. Public Integration Notes

- Public contributors should focus on extending task services through base families (`TextBase`, `AudioBase`, `ImageBase`) and updating `TaskServiceRegistry` mappings.
- Interface contracts and payload schemas are defined in repository source-of-truth modules and OpenAPI specs.
- This document intentionally avoids embedding implementation snippets.

---

## 7. Testing Strategy

- Unit tests should validate preprocess/postprocess behavior and service-level request handling.
- Integration tests should validate orchestrator routing, registry lookup, and multi-service chaining behavior.
- Regression coverage should include mixed task-type pipelines (text/audio/image).

---

## 8. Deployment & Configuration

- Runtime environment variables and deployment manifests are maintained in service-level deployment assets.
- Public contributors should refer to repository deployment guides and environment templates.

---

## 11. Benefits Analysis

| Benefit | Current | Proposed |
|---------|---------|----------|
| **Code Reuse** | ~50% duplication | ~0% duplication |
| **Service Addition Time** | 2-3 hours | 30 minutes |
| **Triton Connections** | N clients | 1 singleton |
| **Testability** | Difficult | Easy (mocked interfaces) |
| **Service Chaining** | Manual | Automatic via config |
| **Maintenance** | High | Low |
| **Scaling** | Per-service | Shared resources |

---

## 12. Migration Plan

### Phase 1: Foundation (Week 1)
- [ ] Create base classes and interfaces
- [ ] Implement shared TritonService
- [ ] Implement TaskServiceRegistry
- [ ] Implement InferenceOrchestrator
- [ ] Write unit tests

### Phase 2: Pilot Service (Week 2)
- [ ] Migrate Transliteration service
- [ ] Integration tests
- [ ] Load testing
- [ ] Documentation

### Phase 3: Rollout (Weeks 3-4)
- [ ] Migrate NMT service
- [ ] Migrate NER service
- [ ] Migrate remaining services
- [ ] Monitor performance
- [ ] Decommission old endpoints

### Phase 4: Optimization (Week 5)
- [ ] Performance tuning
- [ ] Caching optimization
- [ ] Circuit breaker implementation
- [ ] Metrics & monitoring

---

## 13. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Shared inference client bottleneck | Use connection pooling, add async queuing |
| Service dependency failures | Implement circuit breaker, graceful degradation |
| Backward compatibility | Version endpoints, gradual rollout |
| Performance regression | Baseline metrics, load testing before deploy |

---

## 14. Monitoring & Observability

Metrics to track:
- Service latency (per service)
- Triton server response time
- Error rates (per service)
- Service cache hits/misses
- Memory usage (connection pooling)

---

## 15. Future Enhancements

1. **Async Service Parallel Execution**: Execute multiple services in parallel instead of sequential
2. **Result Caching**: Cache Triton responses for repeated inputs
3. **Circuit Breaker Pattern**: Handle Triton server failures gracefully
4. **Service Versioning**: Support multiple versions of same service
5. **Dynamic Service Loading**: Load services from configuration
6. **Result Streaming**: Stream results for long-running services

---

## 16. Decision Points for Architect Review

1. **Parallel vs Sequential Execution**: Should multi-service requests execute services in parallel or sequentially?
2. **Error Handling Strategy**: Should one service failure stop the entire request or continue with others?
3. **Response Format**: Should each service result be isolated or merged into a single response?
4. **Service Discovery**: Should services be registered statically or dynamically?
5. **Triton Connection**: Should we use HTTP or gRPC client? Connection pooling strategy?

---

**Document prepared for architectural review and discussion.**  
**Last updated**: June 1, 2026
