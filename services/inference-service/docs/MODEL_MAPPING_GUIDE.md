# Model Config Mapper (Inference Service)

This guide explains how model-specific tensor mappings work in the new inference flow for `NMT` and `ASR`.

## One-Line Flow

`service_id -> resolve endpoint + adapter_config -> NMT/ASR inference model -> config_mapper resolves value_path/value -> Triton input tensors (dtype/shape/data) -> Triton infer -> tensor outputs -> maps_to semantic keys -> task response`

## Verified Working (as of 2026-05-19)

End-to-end NMT flow tested locally with Postman mock server:
- Request: `POST /api/v1/inference` with `task_type: NMT`, `service_id: indictrans-v2-all`
- Mock MMS returns `adapter_config` with 3 input tensors and 1 output tensor
- Config mapper resolves `value_path` dot-paths and builds Triton payload
- Mock Triton returns `OUTPUT_TEXT: "नमस्ते दुनिया"`
- Response: `{"source": "Hello world", "target": "नमस्ते दुनिया"}`

## Mapping Structure

Model mapping is driven by adapter config declarations:

- `inputs[]`: defines how request/context fields become Triton input tensors.
- `outputs[]`: defines how Triton output tensors become platform semantic keys.

## Input Mappings

Each input tensor declaration contains:

- `tensor`: Triton input tensor name.
- `dtype`: Triton datatype (`BYTES`, `INT32`, `FP32`, etc.).
- `shape`: expected tensor shape (`-1` allowed for dynamic dimensions).
- `value_path` or `value`:
  - `value_path` uses dot-path lookup from context (example: `input.source`).
  - `value` is static constant (or shorthand string path fallback).

### Available Context Keys

Common context:

- `request.config`
- `input`
- `index`

ASR-specific extra context (added by `ASRInferenceModel`):

- `audio.samples`
- `audio.num_samples`
- `audio.sample_rate`

## Intermediate Mappings / Transformations

Before Triton call, mapper performs:

1. Resolve `value_path` (or static `value`) per tensor per item.
2. Cast resolved values to declared `dtype`.
3. Materialize tensor payload:
   - infer/validate shape against declared `shape`,
   - flatten values into `data` list.

Generated intermediate Triton input payload format:

- `triton_inputs[tensor_name] = { "dtype": ..., "shape": [...], "data": [...] }`

And output request list:

- `output_names = [declared output tensor names]`

## Output Mappings

Each output tensor declaration contains:

- `tensor`: tensor name returned by Triton.
- `dtype`: expected output dtype.
- `maps_to`: semantic response key used by platform output.

Mapping behavior:

- Extract tensor by `name` from Triton response.
- Decode bytes if needed.
- Map to semantic key: `tensor -> maps_to`.

Example:

- Triton tensor: `OUTPUT_TEXT`
- Semantic key: `translated_text`
- Final mapped field: `"translated_text": <decoded value>`

## Does the Config Mapper Accept String Arrays?

**Yes — for NMT.** The `value_path` resolves a single string per input item (e.g. `input.source`).
When you send a batch of items, each item's string is collected into a list and materialized as a
`BYTES` tensor with shape `[batch_size, 1]`. So a batch of 3 sentences becomes `data: ["text1", "text2", "text3"]`.

**For ASR — different.** ASR input is not a string array. It is audio data: raw PCM samples
(a float/int array) or a base64-encoded audio payload. The `ASRInferenceModel` adds extra context
(`audio.samples`, `audio.num_samples`, `audio.sample_rate`) via `_build_audio_context` before
the mapper runs. The `value_path` for ASR tensors will point to `audio.samples` or similar —
not a plain string. The mapper handles both cases because `_cast_dtype` recurses into lists.