# Endpoint validation

The model management service can validate inference URLs with a **URL format check** and an optional **live HTTP POST probe**. Logic lives in `validators/endpoint_validator.py`; probe bodies are built in `utils/probe_payloads.py`. Routers call `utils/request_helpers.validate_endpoint_or_raise()` which forwards to `validate_endpoint()`.

## Configuration

| Setting | Environment / source | Default | Description |
|--------|------------------------|---------|-------------|
| `run_inference_test` | `RUN_INFERENCE_TEST` (`AppEnv` in [`ai4icore_env`](../../../libs/ai4icore_env/ai4icore_env/settings.py)) | `true` | When `true`, runs the live probe after the URL check. When `false`, only URL format is validated. |
| `endpoint_validation_mode` | `ENDPOINT_VALIDATION_MODE` (`AppEnv`) | `lenient` | **`lenient`**: HTTP status **&lt; 500** counts as pass (4xx = reachable). **`strict`**: only **&lt; 400** passes (4xx = failure). |
| `endpoint_validation_timeout_seconds` | `ENDPOINT_VALIDATION_TIMEOUT_SECONDS` (`AppEnv`) | `30.0` | Timeout (seconds) for the live inference probe HTTP request. |

Set `RUN_INFERENCE_TEST=false` to skip the live probe (e.g. Triton not reachable from the management network). Use `ENDPOINT_VALIDATION_MODE=strict` when you want registration to **fail on any HTTP 4xx** from the probe (only status **&lt; 400** passes). This is stricter than “reachable” (lenient): it does not inspect the body or require a particular success family such as 2xx—e.g. a **3xx** still passes strict mode because **&lt; 400** is satisfied.

See also `env.template` / `.env` for this service.

## Validation levels

1. **URL format** — Always runs: `http`/`https`, host present, parseable URL (`validate_url_format`).
2. **Live inference test** — Runs when `run_inference_test` is `true` and `task_type` is set. Sends `POST` with `Content-Type: application/json` to the **exact URL** being validated (the service or model `endpoint` field). Skipped (not failed) if `task_type` is missing.

## Where validation runs

| API | Behaviour |
|-----|-----------|
| **`POST /services`** | Validates the **service** `endpoint`. Loads the linked model from the DB for `task.type`, `inferenceEndPoint.schema.request`, and `inferenceEndPoint.schema.response.triton`. |
| **`PATCH /services`** | Same when `endpoint` is updated (and associated model metadata is available). |
| **`POST /models`** | **Live endpoint validation is not run** on create (models can be registered before Triton is up). Endpoint can be checked when **creating/updating a service** or on **model PATCH**. |
| **`PATCH /models`** | Validates `inferenceEndPoint.endpoint` when an endpoint URL is present in the payload. |

## Schema inputs used for the probe (from the model)

Routers pass into `validate_endpoint`:

| Parameter | Source on the model | Purpose |
|-----------|---------------------|---------|
| `task_type` | `task.type` | Chooses built-in ULCA defaults when needed; required for the live test. |
| `request_schema` | `inferenceEndPoint.schema.request` | ULCA-shaped template for wrapper-style APIs (optional). |
| `triton_schema` | `inferenceEndPoint.schema.response.triton` | Tensor names, dtypes, shapes for **Triton V2** JSON probes. |
| `api_key` | Service `api_key` (when validating a service) | Sent as `Authorization: Bearer …` if non-empty. |

If `schema.request` is missing or `{}`, it is not used for shaping the ULCA branch (see below). **`schema.response.triton` is used** whenever it yields a valid Triton V2 body, even when `request` is empty.

### Clarification: `request`, `response`, and what the probe sends

Triton probe construction reads **`inferenceEndPoint.schema.response.triton`** even though validation **sends** an **outbound request** to the inference URL. The following resolves that:

| Question | Answer |
|----------|--------|
| Is the probe built from an HTTP **response** returned by Triton? | **No.** The probe is always an **outbound request** body (`POST` with JSON). Nothing in this flow serializes or replays a prior inference response. |
| Why is tensor metadata under **`schema.response`**? | In the model schema document, `request` and `response` group **contract** material. ULCA usage is under **`request`**. Tensor names, dtypes, and shapes for Triton are stored under **`response.triton`** as **implementation metadata** (an I/O specification). The key name **`response`** reflects that grouping in the JSON model, **not** “read the runtime response body to build the probe.” |
| What is **`schema.request`** used for? | Building the probe when the endpoint expects **ULCA** (Branch B). It is the primary application-level request template. |
| What is **`schema.response.triton`** used for? | Building the probe when the endpoint is **Triton V2** (Branch A): the same tensor names and shapes Triton expects **in the request** you POST. |

In short: **`request`** → ULCA-shaped probe when applicable; **`response.triton`** → Triton V2–shaped probe; both describe what may be **sent**; neither is populated from a **received** inference response during validation.

### Request format vs. Triton tensor metadata

- **`schema.request`** documents the **ULCA** contract (`input`, `config`, `audio`, etc.) for gateway and wrapper services. Use Branch B when the **validated URL** speaks ULCA.

- **Raw Triton** (`POST /v2/models/<name>/infer`) requires the **Triton V2 JSON** structure (`inputs` / `outputs`). That shape differs from ULCA; `request` stays ULCA-only for documentation and downstream consistency.

- **`schema.response.triton`** holds tensor definitions used to assemble a conformant **outbound** Triton request. The parent key `response` is schema placement only.

**Probes follow the protocol of the URL you register.** Prefer Branch A when `response.triton.inputs` is present so ULCA JSON is not POSTed to a raw Triton server (which would fail with errors such as missing `inputs`).

## How the probe payload is built (`utils/probe_payloads.py`)

`build_probe_payload(task_type, request_schema, triton_schema)` returns `(payload, kind)` where `kind` is either `triton_v2` or `ulca`.

### Branch A — Triton V2 (preferred)

If `schema.response.triton` exists and contains a non-empty **`inputs`** list, `build_triton_v2_payload` builds:

```json
{
  "inputs": [ { "name", "datatype", "shape", "data" }, ... ],
  "outputs": [ { "name" }, ... ]
}
```

- **Shapes** may be strings like `[batch_size, 1]` or use `-1`; symbolic or dynamic dimensions are mapped to **`1`** for a minimal valid tensor.
- **BYTES** tensors: dummy data uses a **minimal silent WAV** (base64) for audio-like input names (`AUDIO_DATA`, `audio_data`, …) and a **minimal 1×1 PNG** (base64) for image-like names (`IMAGE_DATA`, `image_data`, …). Other BYTES tensors use empty string data unless overridden by dtype defaults.

This path matches **raw Triton HTTP** endpoints (`/v2/models/.../infer`). It does **not** use `schema.request` for the JSON body.

### Branch B — ULCA (when Triton metadata is missing or unusable)

Used when Branch A does not produce a payload.

1. **Non-empty `schema.request`** — Same top-level rules as before: string → `"test"`, dict copied as-is, empty list → `["test"]`, etc. Empty `{}` is treated as absent.
2. **Built-in task defaults** — `_ULCA_DUMMY_PAYLOADS` in `probe_payloads.py` (per `task.type`, e.g. `nmt`, `asr`, `ner`, `ocr`, …).
3. **Unknown task** — `{"input": [{"source": "test"}]}`.

Built-in defaults are **hardcoded** in `probe_payloads.py`; they are not derived from `languages` or other model fields.

## Pass / fail rules (live test)

Depends on **`endpoint_validation_mode`**:

| Mode | Pass condition |
|------|------------------|
| `lenient` (default) | HTTP status **&lt; 500** |
| `strict` | HTTP status **&lt; 400** |

Connect errors and timeouts fail regardless of mode.

Default probe timeout: **15 seconds**. TLS verification is disabled for the probe client (`verify=False`).

## Logging

Logger: **`endpoint-validator`**.

For each live test you should see:

1. **Outbound** — `Inference probe → <url> task_type=... mode=... kind=<triton_v2|ulca> payload=<...>`
2. **Inbound** — `Inference probe ← <url> status=... body=...` (JSON or first 500 chars of text)
3. **Summary** — `Endpoint validation [passed|failed] for <url> (task=...): <message>`

The success message includes the payload kind, e.g. `HTTP 200 (triton_v2 payload)` or `HTTP 200 (ulca payload)`.

> **Note:** Older docs referred to `build_inference_payload` and log lines like `Using model schema.request for test payload`. Implementation now uses **`build_probe_payload`** in **`utils/probe_payloads.py`** and the log format above.

## API errors on failure

`validate_endpoint_or_raise` raises **HTTP 400** with a structured `detail` dict: **`kind`**: `EndpointValidationError`, **`message`**, and **`errors`**: a list of validation messages.

The service’s HTTP exception handler (see `middleware/error_handler_middleware.py`, registered after shared handlers in `main.py`) serializes that into the standard **`detail`** envelope: **`code`** is taken from **`kind`** (or `code` if present), **`message`** is unchanged, and the **`errors`** list is joined into a single **`details`** string. Clients therefore see `code`, `message`, and `details`—not a separate `errors` array in the JSON body.

## Runtime inference (outside this service)

Downstream services use `ai4icore_model_management` middleware and `TritonClient`, which POST to the **service `endpoint` stored in the DB**. If only a **base URL** is stored (e.g. `http://host:8300`), middleware may **normalize** it to `/v2/models/<model_name>/infer` using model metadata — see `normalize_triton_http_infer_url` in the shared library. That behaviour is **not** part of endpoint validation itself but affects the same stored URLs.

## Related files

| File | Role |
|------|------|
| `validators/endpoint_validator.py` | URL check, `test_inference`, `validate_endpoint` |
| `utils/probe_payloads.py` | `build_probe_payload`, Triton V2 and ULCA builders |
| `utils/request_helpers.py` | `validate_endpoint_or_raise`, wires `AppEnv` |
| `routers/router_services.py` | Service create/update; passes `request_schema` + `triton_schema` from linked model |
| `routers/router_models.py` | Model PATCH validation; **POST /models** skips live probe |
| [`libs/ai4icore_env/.../settings.py`](../../../libs/ai4icore_env/ai4icore_env/settings.py) | `run_inference_test`, `endpoint_validation_mode` |
