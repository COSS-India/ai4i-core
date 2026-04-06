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

- **Services** — `POST /services`: validates `endpoint` using the linked model’s `task.type` and `inferenceEndPoint.schema.request` (when present).
- **Models** — `POST /models` and `PATCH /models`: validates `inferenceEndPoint.endpoint` when an endpoint URL is provided, using the same `run_inference_test` setting.

## Test payloads

Payloads are built by `build_inference_payload`:

1. If the model stores a non-empty `**Schema.request`** object (`request_schema`), the validator walks its top-level keys and fills placeholders: string values become `"test"`, dicts are copied as-is, empty lists become `["test"]`, other types are copied.
2. Otherwise it uses **task-type defaults** (`_DUMMY_PAYLOADS`), e.g. NMT uses `input` + `config.language` with sample text.
3. If the task type is unknown, it falls back to `{"input": [{"source": "test"}]}`.

## Pass / fail rules (live test)

- **Connect / timeout / transport errors** → validation **fails** (endpoint unreachable).
- **HTTP status below 500** (including **4xx**) → **passes**. The probe only checks that something responds; dummy data is not expected to be semantically valid for every deployment.
- **HTTP status 500 or above** → **fails**.

Optional `**api_key`** on the service is sent as `Authorization: Bearer <api_key>` when non-empty.

Default HTTP timeout for the probe is **15 seconds**. TLS verification is disabled for the client (`verify=False`) to match typical internal/Triton setups.

## Logging

Logger name: `**endpoint-validator`**.

For each live test you should see:

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

