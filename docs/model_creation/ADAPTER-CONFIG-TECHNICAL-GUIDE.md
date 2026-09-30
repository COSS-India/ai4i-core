# Adapter Config Technical Guide

How `adapterConfig` in the model JSON drives Triton requests and responses

Audience: engineers onboarding models, platform developers, DevOps / MLOps

## 1. Scope

This document is the reference for the `adapterConfig` block of a model JSON. It covers:

- where the config is stored and how it reaches the inference service
- the complete field schema, with types, defaults and validation rules
- how inputs are rendered into KServe v2 tensors and how outputs are mapped back
- rules specific to each task type
- fields the runtime supports that the current sample files do not use, and Triton features it does not support
- an onboarding procedure and a troubleshooting table
- the `adapterConfig` from each sample model JSON (Appendix)

## 2. Architecture and data flow

### 2.1 Storage

- On `POST` model create, `adapterConfig` is stored under `inference_endpoint.adapterConfig` (JSONB).
- Older rows may use the snake_case key `adapter_config`. Readers accept both; updates rewrite it as `adapterConfig`.
- On `PATCH`, the sent `adapterConfig` is **deep-merged** into the stored one (`_deep_merge`). Nested objects merge key by key. **Lists are replaced wholesale.** Sending `inputs` replaces every input declaration, so always send the full list.
- When a service is resolved, the model's config is exposed to the inference service as `service_info["adapter_config"]`, and `model_name` is lifted out for LLM routing.

### 2.2 Request pipeline (Triton-backed tasks)

1. The orchestrator resolves the service and calls `BaseTaskService.process()`: validate, preprocess, `run_inference`, postprocess.
2. `run_inference` reads the input list from `payload[payload_key]`. The key is `input` for text, `audio` for audio and `image` for images.
3. Call topology: `adapterConfig.call_mode` if set, otherwise the class default `TRITON_CALL_MODE`. With `batch`, the whole list goes in one Triton call. With `per_item`, each item is its own call.
4. `convert_payload_to_triton_format` calls `GenericTritonMapper.compose_triton_kserve_v2_payload`. For every declared input and every item, it builds a context, resolves `value_path` or `value`, casts to `dtype`, resolves `shape`, and emits `{name, datatype, shape, data}`. Large numeric numpy tensors use the binary tensor extension instead.
5. The request is POSTed to `callbackUrl` with the outputs list set to the names in `outputs[].tensor`.
6. `convert_triton_output_to_task_format` runs `map_outputs`, then `to_output_items`. It picks each output by name, decodes bytes, applies `json_field`, renames to `maps_to`, splits the batch into per-item dicts and applies `transform`.
7. `postprocess_output`: if the config declares response shaping (a `response` block, or any output with `response_key` or `pair_with_input`), it runs `shape_output_items` and `build_response_envelope`. Otherwise it uses the default: unwrap scalars, add `source` from the input, and echo `config`.

### 2.3 LLM path

Task `llm` never reaches `GenericTritonMapper`. `OpenAIProxyService` (`services/llm_service.py`) forwards OpenAI-compatible requests to `callbackUrl` + `/v1/...` and uses **only** `adapterConfig.model_name` as the upstream `model`. The `inputs` and `outputs` keys must still be present, because the create-time field validator checks for them, but their contents are not used.

## 3. Schema reference

### 3.1 Top level (AdapterMappingConfig)

| Field | Type | Req. | Default | Behaviour |
|---|---|---|---|---|
| `version` | string | Yes* | - | Schema version, non-empty. Use "1.0". Not interpreted beyond the non-empty check. |
| `model_version` | string | No | "1" | Emitted in trace attributes and model metadata only. **Not** used to build the URL. The version called is whatever `callbackUrl` points to. |
| `inputs` | InputTensorDeclaration[] | Yes | - | min 1 entry (not enforced for llm, but the key must exist). |
| `outputs` | OutputTensorDeclaration[] | Yes | - | min 1 entry (same llm caveat). Order does not matter; lookup is by name. |
| `response` | ResponseEnvelopeDeclaration | No | null | Turns on config-driven response shaping (section 6). |
| `model_name` | string | llm only | - | Upstream model id for the OpenAI proxy. Required for llm at create time. |
| `call_mode` | "batch" \| "per_item" | No | class default | Overrides `TRITON_CALL_MODE`. Any value other than `per_item` means batch. Not validated at create time. |

\* not required for llm.

### 3.2 Input tensor (InputTensorDeclaration)

| Field | Type | Req. | Behaviour |
|---|---|---|---|
| `tensor` | string | Yes | KServe input `name`. Must match the Triton model config exactly (case-sensitive). |
| `dtype` | enum | Yes | One of the supported dtypes (section 3.5). Sent as `datatype` on the wire. |
| `shape` | int[] | Yes | Declared shape; `-1` is a wildcard. Non-empty. Resolved against the data (section 4.4). |
| `value_path` | string | One of | Dot path into the render context (section 4.1). |
| `value` | any | One of | Static value used for every item. If `value` is a string and `value_path` is missing, the string is **reinterpreted as a path** (backward-compatible shorthand). As a result, a constant string tensor cannot be declared today. |

### 3.3 Output tensor (OutputTensorDeclaration)

| Field | Type | Req. | Behaviour |
|---|---|---|---|
| `tensor` | string | Yes | KServe output `name` to request and read. |
| `dtype` | enum | Yes | Validated against the supported set. Not used to cast output values. |
| `maps_to` | string | Yes | Key the value is stored under in each output item. |
| `json_field` | string | No | Parse each value as a JSON object and keep only this field. Non-JSON values, or JSON without the field, pass through unchanged. |
| `transform` | string \| string[] | No | Per-item transform chain, applied left to right (section 5.3). |
| `response_key` | string | No | `output[].<key>` renames `maps_to` to `<key>`. Bare `output[]` splats a dict value into the item. Regex: `output\[\](?:\.(\w+))?`. |
| `pair_with_input` | string | No | Input dot path. Its last segment is copied from the input item at the same index into the output item (camelCase fallback). An output field of the same name wins. |

### 3.4 Response envelope (ResponseEnvelopeDeclaration)

| Field | Type | Default | Behaviour |
|---|---|---|---|
| `task_type` | string | null | If set, the response gets `taskType`. |
| `include_config` | bool | true | Echo the request `config`. `false` omits the key. |
| `config_keys` | string[] | null | Echo only these config keys (missing ones become null). Takes precedence over `include_config`. |
| `static_item_fields` | object | null | Added to every output item with `setdefault` (never overwrites). |

### 3.5 Supported dtypes

`SUPPORTED_TRITON_DTYPES` is defined in both services and must stay in sync: `config_mapper.py` in the inference service and `app/schemas/common.py` in platform-core.

| dtype | Triton config type | Input cast | Seen in samples |
|---|---|---|---|
| `BYTES` | `TYPE_STRING` | `str(v)`; bytes are decoded as UTF-8 | Yes |
| `BOOL` | `TYPE_BOOL` | `bool(v)` | Yes (transliteration) |
| `FP16` / `FP32` / `FP64` | `TYPE_FP16/32/64` | `float(v)`; numpy arrays become float32 | FP32 only |
| `INT8` / `INT16` / `INT32` / `INT64` | `TYPE_INT8..64` | `int(v)`; numpy arrays become int64 | INT32 only |
| `UINT8` / `UINT16` / `UINT32` / `UINT64` | `TYPE_UINT8..64` | `int(v)` | UINT8 only |

Casting is Python-side only. A value that cannot be cast (for example `int("abc")`) raises at render time. `BOOL` uses Python truthiness, so the string "false" becomes `true`. Send real JSON booleans in the request.

## 4. Input rendering

### 4.1 Render context and value_path

For each declared input and each item in the call group, the mapper builds:

```text
{
  "request": { "config": <payload.config> },
  "input":   <current item>,          // payload[payload_key][i]
  "index":   <i>,
  ...context_builder(item, i, config) // task-specific extras, merged at top level
}
```

`value_path` is split on `.` and walked through dict keys or object attributes. If a key is missing, the walker retries with the snake_case segment converted to camelCase (`source_language` becomes `sourceLanguage`). There is no camelCase-to-snake_case fallback, so snake_case paths are the most tolerant. On failure it raises `RuntimeError: Path '<path>' not found (missing key '<part>')`.

Context extras provided by task services (`_triton_context_builder`):

| Service | Extra paths | Notes |
|---|---|---|
| `AudioBase` (ALD, speaker and language diarization) | `audio.audio_content` | Base64 audio of the current item |
| `ASRTaskService` | `audio.samples`, `audio.num_samples`, `audio.sample_rate` | Decoded float PCM (numpy) from `preprocess_input` |
| `TTSTaskService` | none; items are rewritten instead | `preprocess_input` chunks text (400 characters or less) into items carrying `source`, `gender` (`config.gender`, default "female") and `language_id` (from `config.language`) |
| Text / image services | none | Canonical context only |

value_path values used across the samples:

| value_path | Tasks |
|---|---|
| `input.source` | nmt, ner, tts, transliteration, language-detection, llm (placeholder) |
| `input.image_content` | ocr |
| `input.gender`, `input.language_id` | tts |
| `request.config.language.source_language` / `sourceLanguage` | nmt, asr, ner, transliteration |
| `request.config.language.target_language` / `targetLanguage` | nmt, transliteration |
| `request.config.target_language` | language-diarization |
| `request.config.num_speakers` | speaker-diarization |
| `request.config.is_word_level`, `request.config.top_k` | transliteration |
| `audio.audio_content` | audio-lang-detection, speaker/language-diarization |
| `audio.samples`, `audio.num_samples` | asr |

### 4.2 Batching

In `batch` mode, one value is resolved per item and the values form the first dimension of the tensor. Values taken from `request.config` are therefore repeated per item. For example, `INPUT_LANGUAGE_ID` becomes `[["en"],["en"]]` for two texts. In `per_item` mode, each call carries one item, so the batch dimension is 1.

Class defaults: `TRITON_CALL_MODE = "batch"` in `BaseTaskService`, and `"per_item"` in `AudioBase` (all audio tasks) and `TTSTaskService`.

### 4.3 Wire format

Rendered request for the NMT sample with one input item:

```text
POST <callbackUrl>
{
  "inputs": [
    { "name": "INPUT_TEXT",         "datatype": "BYTES", "shape": [1, 1], "data": ["Hello, how are you?"] },
    { "name": "INPUT_LANGUAGE_ID",  "datatype": "BYTES", "shape": [1, 1], "data": ["en"] },
    { "name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1, 1], "data": ["hi"] }
  ],
  "outputs": [ { "name": "OUTPUT_TEXT" } ]
}
```

`data` is always flattened (row-major). Large numeric numpy inputs (currently only ASR `AUDIO_SIGNAL`) are sent through the KServe **binary tensor extension** as little-endian raw bytes. This happens automatically when every item's value is an ndarray of a numeric dtype. Ragged batches fall back to JSON.

### 4.4 Shape resolution

1. If the declared shape has more than one dimension, each scalar item value is wrapped as `[v]`.
2. The actual shape is inferred from the nested lists (`[len, len(first), ...]`).
3. If the inferred shape has fewer dimensions than declared, it is padded with 1s. If it has more, the call fails with `Declared shape X has fewer dims than inferred shape Y`.
4. Each dimension: `-1` takes the inferred size. A fixed size must equal the inferred size, otherwise the call fails with `Declared shape X does not match inferred shape Y`.

| Declared | Triton config it matches | Typical use |
|---|---|---|
| `[-1, 1]` | `max_batch_size > 0`, `dims: [1]` | Batched scalar strings (NMT, NER, OCR, language detection) |
| `[-1, -1]` | `max_batch_size > 0`, `dims: [-1]` | Batched variable-length vectors (ASR samples) |
| `[1, 1]` | per_item with `dims: [1]` and batch dim 1 | Audio tasks, one file per call |
| `[-1]` / `[1]` | `max_batch_size: 0`, `dims: [-1]` / `[1]` | Non-batching models (transliteration, TTS) |

Rule of thumb: if `max_batch_size > 0`, prepend `-1` to Triton's `dims`. If `max_batch_size` is 0, copy `dims` as they are. A fixed `1` in the batch position only works with `per_item` or single-item requests.

## 5. Output mapping

### 5.1 Extraction

For each declared output, the mapper looks up `outputs[]` in the Triton response by `name` and takes `data`. If the response has no `outputs` list, it falls back to a top-level key. A missing tensor raises `RuntimeError: Missing output tensor '<name>'`. Bytes are decoded as UTF-8, then `json_field` is applied if set, and the result is stored under `maps_to`.

### 5.2 Batch split

`to_output_items` sets the batch size to the longest list among the mapped values. Item `i` takes element `i` of each list. A shorter list reuses its last element, and a scalar is repeated for every item.

### 5.3 Transforms

Transforms apply per item, after single-element nesting is removed, in the declared order. Their result is final: later shaping does not unwrap it again.

| Transform | Semantics | Used in samples |
|---|---|---|
| `json_parse` | String starting with `{` or `[` goes through `json.loads`. On failure or non-JSON input, the value passes through. Applied element-wise to lists. | ald, ner, language-detection, language-diarization |
| `wrap_list` | A list is kept; a truthy scalar becomes `[v]`; a falsy scalar becomes `[]`. | language-detection |
| `unwrap_scalar` | Peels single-element list nesting (`[["x"]]` becomes `"x"`). | none |
| `base64_encode` | Value (bytes, or `str(v)` as UTF-8) becomes a base64 string. Element-wise on lists. | none |

## 6. Response shaping

Shaping is config-driven only when `response` is present, or when some output declares `response_key` or `pair_with_input`. Otherwise the default path returns `{"output": [...], "config": <request config>}`, where each item has unwrapped values plus `source` from the input.

Config-driven order, per item:

1. `pair_with_input` fields are copied from the input item at the same index. They come first in the item.
2. Mapped outputs are added. Untransformed values are unwrapped. `response_key: output[].k` renames the key; `output[]` merges a dict value into the item.
3. `response.static_item_fields` are added where absent.
4. Envelope: optional `taskType`, then `output`, then `config` (the `config_keys` subset, the full config, or omitted).

Example from the language-diarization sample. `DIARIZATION_RESULT` holds JSON text, `json_parse` turns it into a dict, and `response_key: output[]` merges its top-level fields into the item. The envelope is `{taskType: "language-diarization", output: [...], config: {serviceId}}`.

## 7. Validation

### 7.1 Create time (platform-core)

`ModelCreateRequest` mirrors the runtime rules so bad configs fail on save instead of on the first call:

- `inputs` and `outputs` keys present (all tasks, including llm)
- llm: `model_name` non-empty; no other checks
- `version` is a non-empty string
- every input has `tensor`, a supported `dtype`, a non-empty `shape`, and `value_path` or `value`
- every output has `tensor`, a supported `dtype` and a non-empty `maps_to`; `transform` in the supported set; `response_key` matches the regex
- tts: some output has `tensor == "OUTPUT_GENERATED_AUDIO"`
- ner: some output has `maps_to == "target"` with `json_parse` in its transform

**Not** validated at create time: that tensor names exist on the Triton model, that value paths resolve, that shapes match Triton, `call_mode`, and the `response` block contents. These surface only when the model is called. Always run a real test inference.

### 7.2 Runtime (inference-service)

`GenericTritonMapper._validate_config` re-checks the same structural rules each time the mapper is built, then rendering and mapping raise on path, cast, shape or missing-output errors (section 10). Unknown keys inside input and output entries are ignored silently (Pydantic default), so a misspelled optional field such as `transfrom` does nothing and gives no error.

## 8. Task-specific behaviour

| Task | classInstance (samples) | Payload key / call mode | Special rules |
|---|---|---|---|
| nmt | `TextDefaultModel` | input / batch | Default response path (no shaping). |
| ner | `NERTaskService` | input / batch | Output `target` must use `json_parse`. |
| transliteration | `TransliterationTaskService` | input / batch | Non-batching shapes `[-1]`. Uses BOOL and UINT8 inputs. |
| language-detection | `LanguageDetectionTaskService` | input / batch | `json_parse` + `wrap_list`, paired with `input.source`. |
| tts | `TTSTaskService` | input / per_item | Text chunked in preprocess. Output read by the literal name `OUTPUT_GENERATED_AUDIO`; `maps_to` is ignored. |
| asr | `ASRTaskService` | audio / per_item | Audio decoded to float PCM. `AUDIO_SIGNAL` goes over the binary extension. |
| audio-lang-detection | `AudioDefaultModel` | audio / per_item | `audio.audio_content` input. |
| speaker-diarization | `SpeakerDiarizationTaskService` | audio / per_item | Config normalised before rendering. |
| language-diarization | `LanguageDiarizationTaskService` | audio / per_item | JSON result splatted via `response_key: output[]`. |
| ocr | `ImageDefaultModel` | image / batch | Text renamed to `source`; static `target: ""`. |
| llm | null | n/a (OpenAI proxy) | Only `model_name` is used. |

`classInstance` sits outside `adapterConfig`, but a wrong value makes every call fail even though the model saves. Copy it from the sample for the task.

## 9. Supported but unused in the samples

All of the following work today without code changes.

| Feature | Use case | Example |
|---|---|---|
| Input `value` (static) | Constant numeric or boolean tensors: beam size, thresholds, flags. **Static strings are not possible:** a string `value` is always reinterpreted as a path. | `{"tensor":"BEAM_SIZE","dtype":"INT32","shape":[-1,1],"value":4}` |
| Output `json_field` | Models returning a JSON envelope where only one field matters (e.g. OCR `full_text`) | `"json_field": "full_text"` |
| `unwrap_scalar` | Models returning `[[x]]` per item that must be a scalar before other transforms | `"transform": ["unwrap_scalar", "json_parse"]` |
| `base64_encode` | Binary outputs (audio, image bytes) that must reach the client as base64 | `"transform": "base64_encode"` |
| `call_mode` | Force `per_item` for a text model that cannot batch, or `batch` for an audio model that can | `"call_mode": "per_item"` |
| `audio.sample_rate` | ASR models taking the sample rate as a tensor | `{"tensor":"SAMPLE_RATE","dtype":"INT32","shape":[-1,1],"value_path":"audio.sample_rate"}` |
| `index` | Models needing item position / sequence IDs within a batch | `"value_path": "index"` |
| dtypes FP16, FP64, INT8, INT16, INT64, UINT16, UINT32, UINT64 | INT64 token IDs, FP16 half-precision models | `"dtype": "INT64"` |
| `response` on other tasks | Any task can set `task_type`, `config_keys`, `static_item_fields` | `"response": {"config_keys": ["serviceId"]}` |

### 9.1 Not supported

| Triton feature | Current behaviour |
|---|---|
| Per-tensor `parameters` (e.g. `binary_data`, `classification`) | Not expressible; unknown keys are ignored. |
| Static string input values | Not possible; a string `value` is treated as a path. Needs a code change (e.g. a separate `static_value` key). |
| Request-level `id` and `parameters` (e.g. sequence batching `sequence_id`, `sequence_start`) | Not emitted. Stateful and sequence models are not supported. |
| Version routing from `model_version` | Not used. Encode it in `callbackUrl` (`/v2/models/<m>/versions/<v>/infer`). |
| Decoupled / streaming models (gRPC stream, generate_stream) | Not supported by the Triton path. |
| Output dtype casting | `dtype` on outputs is validated only; values are passed as returned. |
| Binary output extension | Outputs are read from JSON `data` only. |

## 10. Onboarding procedure

1. Fetch the Triton model config: `curl <host>/v2/models/<model>/config`. Note `max_batch_size` and every `input[]` and `output[]` (`name`, `data_type`, `dims`).
2. Start from the sample for the task (Appendix). Copy `adapterConfig`, `schema` and `classInstance`.
3. Map each Triton input to `inputs[]`: `name` to `tensor`; `data_type` to `dtype` (drop `TYPE_`, `STRING` becomes `BYTES`); `dims` and `max_batch_size` to `shape` (section 4.4); choose a `value_path` from section 4.1 or a static `value`.
4. Map each Triton output to `outputs[]` and keep the `maps_to` names from the sample. The task service and clients depend on them.
5. Add transforms and shaping only where the raw output differs from the sample's contract.
6. Set `callbackUrl` to the full infer URL, including the version if it is pinned.
7. Check the tensors directly against Triton with a hand-built request (section 4.3 format) before registering.
8. Register the model, create the service and run a real inference through the platform. Create-time validation does not catch tensor names, paths or shapes.
9. To change the config later, PATCH with complete `inputs` / `outputs` lists (lists are replaced, not merged).

## 11. Troubleshooting

| Error / symptom | Cause | Fix |
|---|---|---|
| `Path 'x.y' not found (missing key 'y')` | `value_path` does not resolve in the context | Check the payload shape, the payload key and the context extras (4.1) |
| `Input tensor 'X' requires value_path or value` | Neither is set | Add one |
| `Unsupported input dtype 'string'` | Wrong or lowercase dtype | Use a value from 3.5 |
| `Declared shape [..] does not match inferred shape [..]` | Fixed dimension does not match the data (often `[1,1]` with a batch larger than 1) | Use `-1` or `per_item` |
| `Declared shape .. has fewer dims than inferred ..` | Value is nested deeper than declared | Add dimensions to `shape` |
| `Missing output tensor 'Y'` | Output name not in the Triton response | Copy the exact name from the model config |
| Triton 400 `unexpected inference input` / `datatype mismatch` | Tensor name or dtype differs from the Triton config | Align with `/v2/models/<m>/config` |
| `OUTPUT_GENERATED_AUDIO not found` | TTS output tensor has a different name | The model must expose that exact output name |
| NER `model returned non-JSON output` | `json_parse` missing on `target` | Add the transform |
| LLM upstream 404 | `model_name` wrong or missing | Use the id from `<host>/v1/models` |
| Model saves, all calls fail, no clear error | Wrong `classInstance` | Copy it from the sample |
| Optional field has no effect | Misspelled key (ignored silently) | Check spelling against section 3 |

## Appendix: reference adapter configs

The `adapterConfig` from each sample model JSON, extracted with comments removed. Key order is as in the source file.

| File | task.type | classInstance |
|---|---|---|
| ald.json | audio-lang-detection | `AudioDefaultModel` |
| asr.json | asr | `ASRTaskService` |
| audio-lang-detection.json | audio-lang-detection | `AudioDefaultModel` |
| language-detection.json | language-detection | `LanguageDetectionTaskService` |
| language-diarization.json | language-diarization | `LanguageDiarizationTaskService` |
| llm.json | llm | null |
| ner.json | ner | `NERTaskService` |
| nmt.json | nmt | `TextDefaultModel` |
| ocr.json | ocr | `ImageDefaultModel` |
| speaker-diarization.json | speaker-diarization | `SpeakerDiarizationTaskService` |
| transliteration.json | transliteration | `TransliterationTaskService` |
| tts.json | tts | `TTSTaskService` |

### ald.json (task: audio-lang-detection)

classInstance: `AudioDefaultModel`

Identical to audio-lang-detection.json.

```json
{
  "version": "1.0",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "AUDIO_DATA",
      "dtype": "BYTES",
      "shape": [1, 1],
      "value_path": "audio.audio_content"
    }
  ],
  "outputs": [
    {
      "tensor": "LANGUAGE_CODE",
      "dtype": "BYTES",
      "maps_to": "language_code"
    },
    {
      "tensor": "CONFIDENCE",
      "dtype": "FP32",
      "maps_to": "confidence"
    },
    {
      "tensor": "ALL_SCORES",
      "dtype": "BYTES",
      "maps_to": "all_scores",
      "transform": "json_parse"
    }
  ],
  "response": {
    "task_type": "audio-lang-detection",
    "config_keys": [
      "serviceId"
    ]
  }
}
```

### asr.json (task: asr)

classInstance: `ASRTaskService`

audio.samples and audio.num_samples come from ASRTaskService._triton_context_builder. AUDIO_SIGNAL goes over the binary tensor extension.

```json
{
  "inputs": [
    {
      "dtype": "FP32",
      "shape": [-1, -1],
      "tensor": "AUDIO_SIGNAL",
      "value_path": "audio.samples"
    },
    {
      "dtype": "INT32",
      "shape": [-1, 1],
      "tensor": "NUM_SAMPLES",
      "value_path": "audio.num_samples"
    },
    {
      "dtype": "BYTES",
      "shape": [-1, 1],
      "tensor": "LANG_ID",
      "value_path": "request.config.language.source_language"
    }
  ],
  "outputs": [
    {
      "dtype": "BYTES",
      "tensor": "TRANSCRIPTS",
      "maps_to": "transcript",
      "response_key": "output[].source"
    }
  ],
  "version": "1.0",
  "response": {
    "include_config": false,
    "static_item_fields": {
      "nBestTokens": null
    }
  },
  "model_version": "1"
}
```

### audio-lang-detection.json (task: audio-lang-detection)

classInstance: `AudioDefaultModel`

Identical to ald.json.

```json
{
  "version": "1.0",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "AUDIO_DATA",
      "dtype": "BYTES",
      "shape": [1, 1],
      "value_path": "audio.audio_content"
    }
  ],
  "outputs": [
    {
      "tensor": "LANGUAGE_CODE",
      "dtype": "BYTES",
      "maps_to": "language_code"
    },
    {
      "tensor": "CONFIDENCE",
      "dtype": "FP32",
      "maps_to": "confidence"
    },
    {
      "tensor": "ALL_SCORES",
      "dtype": "BYTES",
      "maps_to": "all_scores",
      "transform": "json_parse"
    }
  ],
  "response": {
    "task_type": "audio-lang-detection",
    "config_keys": [
      "serviceId"
    ]
  }
}
```

### language-detection.json (task: language-detection)

classInstance: `LanguageDetectionTaskService`

Uses pair_with_input, so config-driven shaping is active.

```json
{
  "inputs": [
    {
      "dtype": "BYTES",
      "shape": [-1, 1],
      "tensor": "INPUT_TEXT",
      "value_path": "input.source"
    }
  ],
  "outputs": [
    {
      "dtype": "BYTES",
      "tensor": "OUTPUT_TEXT",
      "maps_to": "langPrediction",
      "transform": [
        "json_parse",
        "wrap_list"
      ],
      "pair_with_input": "input.source"
    }
  ],
  "version": "1.0",
  "response": {
    "include_config": false
  },
  "model_version": "1"
}
```

### language-diarization.json (task: language-diarization)

classInstance: `LanguageDiarizationTaskService`

```json
{
  "inputs": [
    {
      "dtype": "BYTES",
      "shape": [1, 1],
      "tensor": "AUDIO_DATA",
      "value_path": "audio.audio_content"
    },
    {
      "dtype": "BYTES",
      "shape": [1, 1],
      "tensor": "LANGUAGE",
      "value_path": "request.config.target_language"
    }
  ],
  "outputs": [
    {
      "dtype": "BYTES",
      "tensor": "DIARIZATION_RESULT",
      "maps_to": "diarization_json",
      "transform": "json_parse",
      "response_key": "output[]"
    }
  ],
  "version": "1.0",
  "response": {
    "task_type": "language-diarization",
    "config_keys": [
      "serviceId"
    ]
  },
  "model_version": "1"
}
```

### llm.json (task: llm)

classInstance: `null`

inputs/outputs are placeholders, ignored by the OpenAI proxy. Only model_name is used.

```json
{
  "version": "1.0",
  "model_name": "google/gemma-4-31B-it",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "INPUT_TEXT",
      "dtype": "BYTES",
      "shape": [1, 1],
      "value_path": "input.source"
    },
    {
      "tensor": "INPUT_LANGUAGE_ID",
      "dtype": "BYTES",
      "shape": [1, 1],
      "value_path": "request.config.language.source_language"
    },
    {
      "tensor": "OUTPUT_LANGUAGE_ID",
      "dtype": "BYTES",
      "shape": [1, 1],
      "value_path": "request.config.language.target_language"
    }
  ],
  "outputs": [
    {
      "tensor": "OUTPUT_TEXT",
      "dtype": "BYTES",
      "maps_to": "target"
    }
  ]
}
```

### ner.json (task: ner)

classInstance: `NERTaskService`

The json_parse on target is required by create-time validation.

```json
{
  "version": "1.0",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "INPUT_TEXT",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "input.source"
    },
    {
      "tensor": "LANG_ID",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "request.config.language.sourceLanguage"
    }
  ],
  "outputs": [
    {
      "tensor": "OUTPUT_TEXT",
      "dtype": "BYTES",
      "maps_to": "target",
      "transform": "json_parse"
    }
  ]
}
```

### nmt.json (task: nmt)

classInstance: `TextDefaultModel`

```json
{
  "version": "1.0",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "INPUT_TEXT",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "input.source"
    },
    {
      "tensor": "INPUT_LANGUAGE_ID",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "request.config.language.source_language"
    },
    {
      "tensor": "OUTPUT_LANGUAGE_ID",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "request.config.language.target_language"
    }
  ],
  "outputs": [
    {
      "tensor": "OUTPUT_TEXT",
      "dtype": "BYTES",
      "maps_to": "target"
    }
  ]
}
```

### ocr.json (task: ocr)

classInstance: `ImageDefaultModel`

Uses version "1" (valid; "1.0" is the convention).

```json
{
  "version": "1",
  "model_version": "1",
  "inputs": [
    {
      "tensor": "IMAGE_DATA",
      "dtype": "BYTES",
      "shape": [-1, 1],
      "value_path": "input.image_content"
    }
  ],
  "outputs": [
    {
      "tensor": "OUTPUT_TEXT",
      "dtype": "BYTES",
      "maps_to": "text",
      "response_key": "output[].source"
    }
  ],
  "response": {
    "static_item_fields": {
      "target": ""
    }
  }
}
```

### speaker-diarization.json (task: speaker-diarization)

classInstance: `SpeakerDiarizationTaskService`

```json
{
  "inputs": [
    {
      "dtype": "BYTES",
      "shape": [1, 1],
      "tensor": "AUDIO_DATA",
      "value_path": "audio.audio_content"
    },
    {
      "dtype": "BYTES",
      "shape": [1, 1],
      "tensor": "NUM_SPEAKERS",
      "value_path": "request.config.num_speakers"
    }
  ],
  "outputs": [
    {
      "dtype": "BYTES",
      "tensor": "DIARIZATION_RESULT",
      "maps_to": "diarization_json"
    }
  ],
  "version": "1.0",
  "model_version": "1"
}
```

### transliteration.json (task: transliteration)

classInstance: `TransliterationTaskService`

```json
{
  "inputs": [
    {
      "dtype": "BYTES",
      "shape": [-1],
      "tensor": "INPUT_TEXT",
      "value_path": "input.source"
    },
    {
      "dtype": "BYTES",
      "shape": [-1],
      "tensor": "INPUT_LANGUAGE_ID",
      "value_path": "request.config.language.sourceLanguage"
    },
    {
      "dtype": "BYTES",
      "shape": [-1],
      "tensor": "OUTPUT_LANGUAGE_ID",
      "value_path": "request.config.language.targetLanguage"
    },
    {
      "dtype": "BOOL",
      "shape": [-1],
      "tensor": "IS_WORD_LEVEL",
      "value_path": "request.config.is_word_level"
    },
    {
      "dtype": "UINT8",
      "shape": [-1],
      "tensor": "TOP_K",
      "value_path": "request.config.top_k"
    }
  ],
  "outputs": [
    {
      "dtype": "BYTES",
      "tensor": "OUTPUT_TEXT",
      "maps_to": "target",
      "pair_with_input": "input.source"
    }
  ],
  "version": "1.0",
  "response": {
    "include_config": false
  },
  "model_version": "1"
}
```

### tts.json (task: tts)

classInstance: `TTSTaskService`

input.gender and input.language_id are injected per chunk by TTSTaskService.preprocess_input. maps_to on OUTPUT_GENERATED_AUDIO is ignored.

```json
{
  "inputs": [
    {
      "dtype": "BYTES",
      "shape": [1],
      "tensor": "INPUT_TEXT",
      "value_path": "input.source"
    },
    {
      "dtype": "BYTES",
      "shape": [1],
      "tensor": "INPUT_SPEAKER_ID",
      "value_path": "input.gender"
    },
    {
      "dtype": "BYTES",
      "shape": [1],
      "tensor": "INPUT_LANGUAGE_ID",
      "value_path": "input.language_id"
    }
  ],
  "outputs": [
    {
      "dtype": "FP32",
      "tensor": "OUTPUT_GENERATED_AUDIO",
      "maps_to": "audio_data"
    }
  ],
  "version": "1.0",
  "model_version": "1"
}
```
