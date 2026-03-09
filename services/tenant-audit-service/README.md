# Tenant Audit Service

The **Tenant Audit Service** is a small FastAPI microservice that lets you inspect
per-tenant request/response tables (NMT, TTS, ASR, OCR, etc.) stored in tenant
schemas in the `multi_tenant_db` PostgreSQL database.

Given a `tenant_id` and a `service` name, it:

- looks up the tenant's `schema_name` from the `tenants` table
- switches the PostgreSQL `search_path` to that schema
- queries the corresponding `*_requests` and `*_results` tables

This is useful for debugging, audit, or ad‑hoc inspection of traffic per tenant.

---

## Service configuration

The service lives in `services/tenant-audit-service` and reads configuration
from `.env` (or environment variables).

### Core env vars

```env
SERVICE_NAME=tenant-audit-service
SERVICE_PORT=9003
SERVICE_HOST=tenant-audit-service
LOG_LEVEL=INFO

# Multi-tenant database connection
DB_USER=dhruva_user
DB_PASSWORD=
DB_HOST=postgres          # use `localhost` when running locally
DB_PORT=5432              # or your local Postgres port
DB_NAME=multi_tenant_db
```

> When running locally outside Docker, set `DB_HOST=localhost` and the correct
> `DB_PORT` (for example `5434`), as you've done in your local `.env`.

The service internally builds:

```text
postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}
```

and uses that to connect to the multi‑tenant database.

---

## Service tables mapping

The service knows how to map logical `service` names to the underlying tables in
each tenant schema (`tenant_<slug>`), using `SERVICE_TABLES` in `main.py`.

Supported `service` values and their tables:

| Service value(s)           | Request table                        | Result table                          |
|---------------------------|--------------------------------------|---------------------------------------|
| `nmt`                     | `nmt_requests`                       | `nmt_results`                         |
| `tts`                     | `tts_requests`                       | `tts_results`                         |
| `asr`                     | `asr_requests`                       | `asr_results`                         |
| `ocr`                     | `ocr_requests`                       | `ocr_results`                         |
| `ner`                     | `ner_requests`                       | `ner_results`                         |
| `llm`                     | `llm_requests`                       | `llm_results`                         |
| `transliteration`         | `transliteration_requests`           | `transliteration_results`             |
| `language_detection`      | `language_detection_requests`        | `language_detection_results`          |
| `audio_language_detection`| `audio_lang_detection_requests`      | `audio_lang_detection_results`        |
| `speaker_diarization`     | `speaker_diarization_requests`       | `speaker_diarization_results`         |
| `language_diarization`    | `language_diarization_requests`      | `language_diarization_results`        |

---

## Running the service locally

From the monorepo root:

```bash
cd services/tenant-audit-service
python -m venv .venv
.venv\Scripts\activate  # on Windows
pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 9003 --reload
```

Make sure your `.env` in `services/tenant-audit-service` points to a running
`multi_tenant_db` Postgres that already has:

- `public.tenants` table with `tenant_id` and `schema_name`
- tenant schema (e.g. `tenant_new_acme_corp_5f4bf7`) created and provisioned
  by the multi‑tenant feature (NMT/TTS/ASR/etc. request/result tables).

---

## Running with Docker

From the monorepo root:

- docker compose -f docker-compose-local.yml up --build -d tenant-audit-service

The container listens on port `9003` and exposes:

- `GET /health`
- `GET /api/v1/tenant-service-data`
- `GET /api/v1/tenant-service-data/all`

---

## API Endpoints

### 1. Health check

**Endpoint**

```http
GET /health
```

**Response**

```json
{
  "status": "healthy",
  "service": "tenant-audit-service"
}
```

---

### 2. Get latest request/result rows

Returns **only the latest entry** (by `created_at DESC`) from the per‑tenant
request and result tables.

**Endpoint**

```http
GET /api/v1/tenant-service-data
```

**Query parameters**

- `tenant_id` (string, required): logical tenant identifier, e.g.
  `new-acme-corp-5f4bf7`.
- `service` (string, required): one of the values in the service table above
  (e.g. `nmt`, `asr`, `language-detection`, `audio_language_detection`, etc.).

**Example**

```bash
curl "http://localhost:9003/api/v1/tenant-service-data?tenant_id=new-acme-corp-5f4bf7&service=nmt"
```

**Response (shape)**

```json
{
  "tenant_id": "new-acme-corp-5f4bf7",
  "schema_name": "tenant_new_acme_corp_5f4bf7",
  "service": "nmt",
  "request_table": "nmt_requests",
  "result_table": "nmt_results",
  "requests": [
    { "...": "latest request row" }
  ],
  "results": [
    { "...": "latest result row" }
  ]
}
```

`requests` and `results` will each contain at most **one** row.

---

### 3. Get all request/result rows

Returns **all rows** from the per‑tenant request and result tables, ordered by
`created_at DESC`.

**Endpoint**

```http
GET /api/v1/tenant-service-data/all
```

**Query parameters**

- `tenant_id` (string, required)
- `service` (string, required) — same allowed values as above.

**Example**

```bash
curl "http://localhost:9003/api/v1/tenant-service-data/all?tenant_id=new-acme-corp-5f4bf7&service=asr"
```

**Response (shape)** — same as the latest endpoint, but `requests` and
`results` can contain **many** rows:

```json
{
  "tenant_id": "new-acme-corp-5f4bf7",
  "schema_name": "tenant_new_acme_corp_5f4bf7",
  "service": "asr",
  "request_table": "asr_requests",
  "result_table": "asr_results",
  "requests": [
    { "...": "most recent request" },
    { "...": "older request" }
  ],
  "results": [
    { "...": "most recent result" },
    { "...": "older result" }
  ]
}
```

> Note: if a tenant has a very large number of rows, this endpoint can return a
> large payload. For heavy usage, consider re‑introducing a `limit` and/or
> pagination.

---

## Error handling

- If `tenant_id` is not found in `public.tenants`:

  ```json
  {
    "detail": "Tenant with tenant_id '<id>' not found"
  }
  ```

- If `service` is not one of the supported values:

  ```json
  {
    "detail": "Unsupported service '<value>'. Supported values are: nmt, tts, asr, ..."
  }
  ```

Both endpoints return standard FastAPI error responses with HTTP 4xx/5xx codes
for invalid input or unexpected database errors.

