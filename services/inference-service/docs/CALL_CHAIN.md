# Inference Service — Call Chain

## Overview

The inference pipeline follows the **Template Method** pattern. `BaseTaskService.process()` orchestrates the fixed sequence; each layer contributes only what it owns.

```
HTTP Request
    │
    ▼
routes/inference.py
    │  POST /api/v1/{task}/inference
    ▼
orchestrator/orchestrator.py
    │  TaskFactory.create_service(task_type)  →  TextDefaultModel (for NMT)
    │  service.process(payload)
    ▼
BaseTaskService.process()                [interfaces/task_service.py]
    │  (inherited by TextBase and TextDefaultModel — no override)
    │
    ├─ 0. _deserialize_payload(payload)        ← TextBase override
    │         converts raw dict → SimpleNamespace
    │         so process() getattr/setattr calls work
    │         → request: SimpleNamespace(input=[...], config={...})
    │
    ├─ 1. validate_request(request)            ← TextBase (+ model class override)
    │         └── super() → BaseTaskService.validate_request   # None check
    │         + input and config presence check (getattr)
    │         [model class adds task-specific checks via opt-in helpers]
    │
    ├─ 2. preprocess_input(request.input)      ← TextBase
    │         └── super() → BaseTaskService.preprocess_input   # empty check
    │         + extract_field_from_items(input_data, "source") [BaseTaskService helper]
    │         + _sanitize_source()     → None/empty→" ", \n→" ", strip (per item)
    │         → returns List[Dict] with sanitized source + _chunk index
    │         [model class override adds task-specific enrichment, e.g. script codes]
    │         result written back to request.input via setattr
    │
    └─ 3. run_inference(request)               ← BaseTaskService
               │  (inherited — no TextBase or model class override needed for generic flow)
               │
               ├─ _run_triton_with_mapper(request)             [BaseTaskService]
               │       │
               │       ├─ _get_from_payload(request, "config") [BaseTaskService helper]
               │       │       → config_raw: dict
               │       │
               │       ├─ _get_from_payload(request, "input")  [BaseTaskService helper]
               │       │       → input_data: List[Dict]
               │       │
               │       ├─ SimpleNamespace(**config_raw)
               │       │       → config object for _resolve_service_and_model
               │       │
               │       ├─ _resolve_service_and_model(config)   [BaseTaskService]
               │       │       └── InferenceServerResolver.resolve_service(service_id)
               │       │           → (service_id, model_name, triton_endpoint, api_key, adapter_config)
               │       │
               │       ├─ extract_field_from_items(input_data, "source")  [BaseTaskService]
               │       │       → source_texts: List[str]
               │       │
               │       ├─ GenericTritonMapper(adapter_config)
               │       │       └── compose_triton_kserve_v2_payload(input_data, config)
               │       │           → triton_inputs, triton_outputs
               │       │
               │       ├─ _call_triton_inference(endpoint, inputs, output_names, api_key)  [BaseTaskService]
               │       │       └── HTTP POST → Triton Inference Server
               │       │           → raw_output
               │       │
               │       ├─ GenericTritonMapper.map_outputs(raw_output)
               │       │       → mapped (semantic keys + bytes decoded to UTF-8)
               │       └─ GenericTritonMapper.to_output_items(mapped)
               │           → response_data: List[Dict]
               │           → returns {response_data, source_texts, service_id}
               │
               ├─ log: inference completed: service_id=...
               │
               └─ postprocess_output(result_dict)              ← stub in TextBase
                       [model class implements using opt-in helpers:]
                       _pair_with_sources(response_items, source_texts) → List[Dict]
                       + task-specific schema wrapping (e.g. TranslationOutput)
                       → task-specific response model
                               │
                               ▼
                       HTTP 200
```

---

## Layer Responsibilities

### `routes/inference.py`
Receives the HTTP request, extracts `task_type` and raw payload, delegates to the orchestrator.

### `orchestrator/orchestrator.py`
Calls `TaskFactory.create_service(task_type)` to obtain the correct service instance, then calls `service.process(payload)`.

### `TaskFactory` — `factory/task_factory.py`
- `"NMT"` → `TextDefaultModel()`
- All other task types → `InlineMockService` (stub)
- Services are cached after first instantiation.

### `BaseTaskService` — `interfaces/task_service.py`
Owns the full generic pipeline and shared helpers reused by all layers.

**Pipeline methods:**
- `process()` — template method; calls `_deserialize_payload` → `validate_request` → `preprocess_input` → `run_inference`
- `_deserialize_payload()` — passthrough in base; overridden by TextBase
- `validate_request()` — None check
- `preprocess_input()` — empty check
- `run_inference()` — `_run_triton_with_mapper` → `postprocess_output`; logs `service_id`
- `postprocess_output()` — passthrough in base; stub in TextBase; model class implements

**Shared helpers:**
- `extract_field_from_items(items, field_name)` — extracts a named field from `List[Dict | obj]`
- `_get_from_payload(payload, key, default)` — field access on either dict or object
- `_resolve_service_and_model(config)` — attribute-access version; resolves via `InferenceServerResolver`
- `_call_triton_inference(...)` — HTTP POST to Triton endpoint
- `_run_triton_with_mapper(payload)` — full Triton pipeline using `GenericTritonMapper`

### `TextBase` — `services/base/text_base.py`
Adapts the generic pipeline for text (dict-based) payloads. No task-specific logic.

**Overrides:**
- `_deserialize_payload()` — converts raw dict → `SimpleNamespace` (adapter for `process()` getattr/setattr)
- `validate_request()` — calls super(), adds input/config presence check
- `preprocess_input()` — calls super(), then: `extract_field_from_items` → `_sanitize_source` per item → `_chunk` index
- `postprocess_output()` — `...` stub; model class implements using opt-in helpers

**Text input helpers (called from pipeline):**
- `_sanitize_source(text)` — None/empty → `" "`, `\n` → `" "`, `.strip()`
- `_chunk_inputs(items, size)` — splits into max-`size` batches (opt-in for model class)

**Postprocess helpers (opt-in, called from model class):**
- `_pair_with_sources(response_items, source_texts)` — zips output items with source texts
- `_normalize_text(text)` — collapses whitespace runs, strips ends

### `TextDefaultModel` — `services/models/text_default_model.py`
Stub class. Will override only NMT-specific concerns:
- `validate_request` — language pair check, source ≠ target
- `preprocess_input` — script code resolution (e.g. `hi` → `hi_Deva`) per segment
- `postprocess_output` — calls `_pair_with_sources()`, wraps into `TranslationOutput`
- `run_inference` — calls `super()`, wraps result in `NMTInferenceResponse`

### `GenericTritonMapper` — `services/base/config_mapper.py`
Config-driven tensor resolution. Reads `AdapterMappingConfig` (inputs/outputs declarations) to:
- Resolve `value_path` dot-paths against a context of `{request, input, index}` — supports both dict and attribute access
- Materialise tensors into KServe v2 shape + data format
- Map Triton output tensor names to semantic keys (`maps_to`)
- Decode `bytes` → UTF-8 on all output values via `_decode_output_value()` — **only place bytes decoding happens**
- Convert mapped outputs into `List[Dict]` via `to_output_items()`

No model-specific logic — the same mapper works for any adapter-config-driven task.

---

## `_run_triton_with_mapper` Return Shape

```python
{
    "response_data": List[Dict],   # mapper.to_output_items() result — bytes already decoded
    "source_texts":  List[str],    # extracted source field values
    "service_id":    str,          # resolved service ID
}
```

---

## Adding a New Text Task

1. Create `models/schemas/{task}.py` — request, config, response schemas.
2. Create `services/models/{task}_model.py` — subclass `TextBase`. Override only what differs:
   - `validate_request` — call `super()` first, add task-specific checks
   - `preprocess_input` — call `super()` first, then add task-specific enrichment
   - `postprocess_output` — call `_pair_with_sources()` + wrap in typed schema
   - `run_inference` — call `super()` + wrap result in typed response model
3. Register in `factory/task_factory.py`.
4. Provide an `AdapterMappingConfig` for the task's Triton model — no code change needed for tensor mapping.

## Adding Audio / Image Tasks (Future)

`AudioBase` already exists at `services/base/audio_base.py` (branch: `inference-model-asr`).
Create `services/base/image_base.py` as a sibling of `TextBase`, subclassing `BaseTaskService`.
Concrete task models subclass the relevant modality base.
