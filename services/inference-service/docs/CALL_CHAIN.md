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
    │  TaskFactory.create_service(task_type)  →  NMTTaskService (for NMT)
    │  service.process(payload)
    ▼
BaseTaskService.process()                [interfaces/task_service.py]
    │  (inherited by TextBase and task service — no override)
    │  Raw Dict[str, Any] flows through the entire pipeline — no deserialization step
    │
    ├─ 1. validate_request(payload)            ← TextBase (+ task service override)
    │         └── super() → BaseTaskService.validate_request   # None check
    │         + input and config presence check (dict .get())
    │         [task service adds task-specific checks via super() chain]
    │
    ├─ 2. preprocess_input(payload['input'])   ← TextBase
    │         └── super() → BaseTaskService.preprocess_input   # empty check
    │         + extract_field_from_items(input_data, "source") [BaseTaskService helper]
    │         + _sanitize_source()     → None/empty→" ", \n→" ", strip (per item)
    │         → returns List[Dict] with sanitized source + _chunk index
    │         result written back to payload['input']
    │
    └─ 3. run_inference(payload)               ← BaseTaskService
               │  (inherited — no TextBase or task service override needed for generic flow)
               │
               ├─ execute_triton_inference(payload, model_class)   [BaseTaskService]
               │       │
               │       ├─ payload.get('input')         → input_items: List[Dict]
               │       ├─ payload.get('config')        → config_data: Dict
               │       │
               │       ├─ model_class(adapter_config)
               │       │       → inference_model instance
               │       │
               │       ├─ extract_field_from_items(input_items, "source")  [BaseTaskService]
               │       │       → source_texts: List[str]
               │       │
               │       ├─ inference_model.convert_payload_to_triton_format(input_items, config_data)
               │       │       → triton_inputs, triton_outputs
               │       │
               │       ├─ _call_triton_inference(endpoint, inputs, output_names, api_key)  [BaseTaskService]
               │       │       └── HTTP POST → Triton Inference Server
               │       │           → raw_output
               │       │
               │       └─ inference_model.convert_triton_output_to_task_format(raw_output)
               │               → response_data: List[Dict]
               │               → returns {response_data, source_texts, service_id}
               │
               ├─ postprocess_output(response_data, source_texts=...)   ← task service
               │       [uses opt-in helpers:]
               │       _pair_with_sources(response_items, source_texts) → List[Dict]
               │       + task-specific schema wrapping (e.g. TranslationOutput)
               │
               └─ _build_response(payload, postprocessed)              ← task service
                       → task-specific response model (e.g. NMTInferenceResponse)
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
- `"NMT"` → `NMTTaskService()`
- All other task types → `InlineMockService` (stub)
- Services are cached after first instantiation.

### `BaseTaskService` — `interfaces/task_service.py`
Owns the full generic pipeline and shared helpers reused by all layers.

**Pipeline methods:**
- `process()` — template method; calls `validate_request` → `preprocess_input` → `run_inference`
- `validate_request()` — None check
- `preprocess_input()` — empty check
- `run_inference()` — `execute_triton_inference` → `postprocess_output` → `_build_response`

**Shared helpers:**
- `extract_field_from_items(items, field_name)` — extracts a named field from `List[Dict | obj]`
- `execute_triton_inference(payload, model_class)` — full Triton pipeline: convert → call → parse
- `_call_triton_inference(...)` — HTTP POST to Triton endpoint

### `TextBase` — `services/base/text_base.py`
Implements the text-specific pipeline steps. No task-specific logic.

**Overrides:**
- `validate_request(payload)` — calls super(), adds input/config presence check (dict `.get()`)
- `preprocess_input(input_data)` — calls super(), then: `extract_field_from_items` → `_sanitize_source` per item → `_chunk` index

**Text input helpers (called from pipeline):**
- `_sanitize_source(text)` — None/empty → `" "`, `\n` → `" "`, `.strip()`
- `_chunk_inputs(items, size)` — splits into max-`size` batches (opt-in for task service)

**Postprocess helpers (opt-in, called from task service):**
- `_pair_with_sources(response_items, source_texts)` — zips output items with source texts
- `_normalize_text(text)` — collapses whitespace runs, strips ends

### Task Services — `services/models/text_models.py`
Concrete implementations: `NMTTaskService`, `NERTaskService`, `TransliterationTaskService`, `LanguageDetectionTaskService`.

Each subclasses `TextBase` and overrides only what it owns:
- `validate_request(payload)` — call `super()` first, add task-specific checks (dict `.get()` throughout)
- `postprocess_output(response_items, source_texts)` — call `_pair_with_sources()` + wrap in typed schema
- `_build_response(payload, postprocessed)` — wrap in typed response model
- `_get_inference_model_class()` — returns `GenericTritonMapper`

### `GenericTritonMapper` — `services/base/config_mapper.py`
Config-driven tensor resolution. Reads `AdapterMappingConfig` (inputs/outputs declarations) to:
- Resolve `value_path` dot-paths against a context of `{input, config}` — supports both dict and attribute access
- Materialise tensors into KServe v2 shape + data format
- Map Triton output tensor names to semantic keys (`maps_to`)
- Decode `bytes` → UTF-8 on all output values via `_decode_output_value()` — **only place bytes decoding happens**
- Convert mapped outputs into `List[Dict]` via `to_output_items()`

No model-specific logic — the same mapper works for any adapter-config-driven task.

---

## `execute_triton_inference` Return Shape

```python
{
    "response_data": List[Dict],   # mapper.to_output_items() result — bytes already decoded
    "source_texts":  List[str],    # extracted source field values
    "service_id":    str,          # resolved service ID
}
```

---

## Adding a New Text Task

1. Create `models/schemas/{task}.py` — request config, response schemas.
2. Add a new class in `services/models/text_models.py` subclassing `TextBase`. Override only what differs:
   - `validate_request(payload)` — call `super()` first, add task-specific checks using `payload.get()`
   - `postprocess_output(response_items, source_texts)` — call `_pair_with_sources()` + wrap in typed schema
   - `_build_response(payload, postprocessed)` — wrap in typed response model
   - `_get_inference_model_class()` — return `GenericTritonMapper` (or a custom mapper)
3. Register in `factory/task_factory.py`.
4. Provide an `AdapterMappingConfig` for the task's Triton model — no code change needed for tensor mapping.

## Adding Audio / Image Tasks (Future)

Create `services/base/audio_base.py` or `services/base/image_base.py` as a sibling of `TextBase`, subclassing `BaseTaskService`.
Concrete task models subclass the relevant modality base.
