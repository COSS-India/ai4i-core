# Endpoint validation

The model management service validates inference URLs when you **create or update models** (inference endpoint on the model) and when you **create services** (service endpoint). Validation is implemented in `validators/endpoint_validator.py`.

## Configuration


| Setting              | Source                                                                                                        | Default | Description                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------- |
| `run_inference_test` | `RUN_INFERENCE_TEST` env (via `[ai4icore_env](../../../libs/ai4icore_env/ai4icore_env/settings.py)` `AppEnv`) | `true`  | When `true`, runs the live HTTP inference probe after the URL format check. When `false`, only URL format is validated. |


Set `RUN_INFERENCE_TEST=false` in `.env` or the container environment to skip the live probe (for example when Triton is not reachable from the management service network).

Documented placeholders: `env.template` and `.env` in this service.

## Validation levels

1. **URL format** — Always runs. Ensures `http`/`https`, host present, and parseable URL.
2. **Live inference test** — Runs when `run_inference_test` is `true` and the model has a `task_type`. Sends a JSON `POST` to the configured endpoint with a test payload (see below). Skipped if `task_type` is missing (recorded as skipped, not failed).

## Where it runs

- **Services** — `POST /services`: validates the **service** `endpoint` URL (not the model’s stored inference URL). It loads the linked model for `task.type` and `inferenceEndPoint.schema.request` only to build the probe body.
- **Models** — `POST /models` and `PATCH /models`: validates `inferenceEndPoint.endpoint` when an endpoint URL is provided, using the same `run_inference_test` setting.

### Inference schema on the model

The full `inferenceEndPoint.schema` object may include `modelProcessingType`, `model_name`, `request`, `response`, and other fields. **Endpoint validation only reads `schema.request`** when building the POST body. It does not use `schema.response` or other keys for the probe.

## Test payloads

Payloads are built by `build_inference_payload(task_type, request_schema)` in this order:

### 1. Non-empty `schema.request` (model template)

If `inferenceEndPoint.schema.request` is a **non-empty** object (at least one top-level key), the validator uses it as a **shape template** only at the **top level**:

| Value in `schema.request` (top-level) | Sent in the probe |
| ---------------------------------------- | ----------------- |
| `string` | Replaced with `"test"` |
| `dict` | Copied **as-is** (nested strings are **not** rewritten) |
| `list` | Kept if non-empty; if **empty**, replaced with `["test"]` |
| Other (number, bool, `null`) | Copied as-is |

So sample sentences for translation or other tasks only appear in the probe if they are **inside nested structures** you store under `schema.request` (for example inside `input` / `config` objects). Top-level string fields are always normalized to `"test"`.

An empty object `request: {}` is treated as **missing** (falsy in code), so the flow falls through to task defaults below.

### 2. Task-type defaults (`_DUMMY_PAYLOADS`)

If `schema.request` is missing, empty `{}`, or results in an empty payload after the rules above, the probe uses a **fixed** default per `task.type` (for example NMT includes `input` with `"Hello, how are you?"` and sample `config.language`). These strings are **hardcoded** in `endpoint_validator.py`, not taken from the model’s `languages` or other metadata.

### 3. Unknown task type

If the task type has no entry in `_DUMMY_PAYLOADS`, the probe uses `{"input": [{"source": "test"}]}`.

### What is not used for the probe

The validator does **not** pull text or language choices from:

- `languages` on the model
- `description`, `benchmarks`, or submitter fields
- Any field outside `inferenceEndPoint.schema.request` (for payload shape)

To make the live test resemble a real request, put a representative JSON skeleton (including nested sample text if needed) in **`inferenceEndPoint.schema.request`**.

## Pass / fail rules (live test)

- **Connect / timeout / transport errors** → validation **fails** (endpoint unreachable).
- **HTTP status below 500** (including **4xx**) → **passes**. The probe only checks that something responds; dummy data is not expected to be semantically valid for every deployment.
- **HTTP status 500 or above** → **fails**.

Optional `api_key` on the service is sent as `Authorization: Bearer <api_key>` when non-empty.

Default HTTP timeout for the probe is **15 seconds**. TLS verification is disabled for the client (`verify=False`) to match typical internal/Triton setups.

## Logging

Logger name: `endpoint-validator`.

**Payload source** (from `build_inference_payload`, before the HTTP call):

- When a non-empty model `schema.request` produced the body: `Using model schema.request for test payload (task_type=...): {...}`
- When task defaults are used (`schema.request` empty/missing or not applicable): `Using built-in dummy payload for task_type=... (model schema.request is empty or not provided)`
- When the task type has no built-in dummy: `Using generic fallback payload for unknown task_type=... (no model schema.request, no built-in dummy): {...}`

**Per live test** you should also see:

1. **Request** — `Inference test request to <url>: task_type=..., payload=...`
2. **Response** — `Inference test response from <url>: status=..., body=...`  
   Body is parsed as JSON when possible; otherwise up to 500 characters of text, or `(empty)` if there is no body.

A separate line logs the overall result: `Endpoint validation [passed|failed] for <url> (task=...): <message>`.

## API errors

When validation fails, the API returns **400** with `kind` / `code` `EndpointValidationError` and a list of human-readable messages. The global HTTP exception handler maps the `errors` array into the response `details` field (string) for clients.

## Related files

- `validators/endpoint_validator.py` — validation logic and payloads
- `routers/router_services.py` — service create validation
- `routers/router_models.py` — model create/update validation
- `libs/ai4icore_env/ai4icore_env/settings.py` — `run_inference_test` on `AppEnv`

