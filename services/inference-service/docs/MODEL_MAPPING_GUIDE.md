# Model Mapping Guide (Inference Service)

This guide explains how model-specific tensor mappings work in the new inference flow for `NMT` and `ASR`.

## One-Line Flow

`service_id -> resolve endpoint + adapter_config -> NMT/ASR inference model -> config_mapper resolves value_path/value -> Triton input tensors (dtype/shape/data) -> Triton infer -> tensor outputs -> maps_to semantic keys -> task response`

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