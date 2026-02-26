# Multi-Tenant Service Registration

This guide explains how to fix **"SERVICE_UNAVAILABLE"** errors when running inference (e.g. NMT, TTS, ASR, or other AI services). If you see a response like:

```json
{
    "detail": {
        "message": "NMT service is not active at the moment. Please contact your administrator",
        "code": "SERVICE_UNAVAILABLE"
    }
}
```

the platform’s multi-tenant service registry does not yet have the corresponding service registered. Registering the required services via the Multi-Tenant API resolves this.

---

## When to do this

- **After setup**: Once the platform is running (see [Setup Guide](SETUP_GUIDE.md)), register the services below before calling any inference endpoints.
- **Sandbox / hosted**: When using a hosted environment (e.g. `https://sandbox.ai4inclusion.org`), an administrator must register these services for your tenant.
- **Local**: When using the local stack, you can register them yourself using an admin token.

---

## 1. Get an auth token

You need a **Bearer token** (JWT) to call the multi-tenant register endpoint. Use either **login** (email/password) or an existing **API key**, depending on how your environment is configured.

### Option A: Login (email/password)

**Endpoint:** `POST /api/v1/auth/login`

**Local (API Gateway on port 9000):**
```bash
curl -X POST 'http://localhost:9000/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@ai4inclusion.org","password":"Admin@123"}'
```

**Sandbox:**
```bash
curl -X POST 'https://sandbox.ai4inclusion.org/api/v1/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}'
```

From the JSON response, copy the **`access_token`** value. Use it in the `Authorization` header as `Bearer <access_token>` in the next step.

### Option B: Use an API key

If your deployment accepts API keys for multi-tenant admin operations, use your API key in the request (as per your environment’s docs). For the **register services** endpoint, typically a **Bearer JWT** from login (Option A) is used.

---

## 2. Install curl (if needed)

You need `curl` to run the registration commands below.

| Platform | How to install |
|----------|----------------|
| **Linux (Debian/Ubuntu)** | `sudo apt-get update && sudo apt-get install curl` |
| **Linux (RHEL/CentOS/Fedora)** | `sudo yum install curl` or `sudo dnf install curl` |
| **macOS** | Usually pre-installed. If not: `brew install curl` ([Homebrew](https://brew.sh)) |
| **Windows** | Install [Windows curl](https://curl.se/windows/) or use **Windows 10+** built-in curl (run `curl` in PowerShell/CMD). Alternatively use [Git for Windows](https://gitforwindows.org/) (includes curl in Git Bash). |

Verify:
```bash
curl --version
```

---

## 3. Register services

Register each service with the Multi-Tenant **Register Services** API. One request per service.

**Endpoint:** `POST /api/v1/multi-tenant/register/services`

**Required services to register (all of them):**

| service_name | unit_type | Notes |
|--------------|-----------|--------|
| `tts` | `minute` | Text-to-Speech |
| `asr` | `minute` | Automatic Speech Recognition |
| `nmt` | `minute` | Neural Machine Translation |
| `llm` | `minute` | Large Language Model |
| `pipeline` | `minute` | Pipeline |
| `ocr` | `minute` | Optical Character Recognition |
| `ner` | `minute` | Named Entity Recognition |
| `speech_to_speech_pipeline` | `minute` | Speech-to-Speech Pipeline |
| `transliteration` | `minute` | Transliteration |
| `language_detection` | `minute` | Language Detection |
| `speaker_diarization` | `minute` | Speaker Diarization |
| `language_diarization` | `minute` | Language Diarization |
| `audio_language_detection` | `minute` | Audio Language Detection |

Use the same body shape for each; only `service_name` changes. Replace `YOUR_ACCESS_TOKEN` with the token from step 1, and adjust the base URL for your environment.

### Linux / macOS (bash)

**Local (API Gateway at port 9000):**
```bash
BASE_URL="http://localhost:9000"
TOKEN="YOUR_ACCESS_TOKEN"

for SERVICE in tts asr nmt llm pipeline ocr ner speech_to_speech_pipeline transliteration language_detection speaker_diarization language_diarization audio_language_detection; do
  curl -s -X POST "${BASE_URL}/api/v1/multi-tenant/register/services" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "{
      \"service_name\": \"${SERVICE}\",
      \"unit_type\": \"minute\",
      \"price_per_unit\": 0.00010,
      \"currency\": \"INR\",
      \"is_active\": true
    }"
  echo ""
done
```

**Sandbox:**
```bash
BASE_URL="https://sandbox.ai4inclusion.org"
TOKEN="YOUR_ACCESS_TOKEN"

for SERVICE in tts asr nmt llm pipeline ocr ner speech_to_speech_pipeline transliteration language_detection speaker_diarization language_diarization audio_language_detection; do
  curl -s -X POST "${BASE_URL}/api/v1/multi-tenant/register/services" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "{
      \"service_name\": \"${SERVICE}\",
      \"unit_type\": \"minute\",
      \"price_per_unit\": 0.00010,
      \"currency\": \"INR\",
      \"is_active\": true
    }"
  echo ""
done
```

### Windows (PowerShell)

**Local:**
```powershell
$baseUrl = "http://localhost:9000"
$token = "YOUR_ACCESS_TOKEN"
$services = @("tts","asr","nmt","llm","pipeline","ocr","ner","speech_to_speech_pipeline","transliteration","language_detection","speaker_diarization","language_diarization","audio_language_detection")

foreach ($svc in $services) {
  $body = @{
    service_name = $svc
    unit_type = "minute"
    price_per_unit = 0.00010
    currency = "INR"
    is_active = $true
  } | ConvertTo-Json
  Invoke-RestMethod -Uri "$baseUrl/api/v1/multi-tenant/register/services" -Method Post -Headers @{ "Content-Type"="application/json"; "Authorization"="Bearer $token" } -Body $body
}
```

**Sandbox:** set `$baseUrl = "https://sandbox.ai4inclusion.org"` and use your sandbox token in `$token`.

### Single-service example (any OS)

Register one service (e.g. `pipeline`) with a single curl call:

```bash
curl --location 'http://localhost:9000/api/v1/multi-tenant/register/services' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer YOUR_ACCESS_TOKEN' \
  --data '{
    "service_name": "pipeline",
    "unit_type": "minute",
    "price_per_unit": 0.00010,
    "currency": "INR",
    "is_active": true
  }'
```

For **sandbox**, replace the URL with `https://sandbox.ai4inclusion.org/api/v1/multi-tenant/register/services` and use your sandbox token.

- **201 Created**: Service registered; repeat for other services if you are not using the loop/script.
- **409 Conflict**: Service already exists; you can skip that service.
- **401 Unauthorized**: Token missing or invalid; get a new token (step 1).

---

## 4. Verify

After registering all services, call the inference endpoint that was returning `SERVICE_UNAVAILABLE`. It should succeed (or return a different, non-registration-related error if something else is wrong).

---

## Summary

| Step | Action |
|------|--------|
| 1 | Get Bearer token via `POST /api/v1/auth/login` (or use API key if supported). |
| 2 | Install `curl` if needed (see table for Linux/macOS/Windows). |
| 3 | For each of the 13 services, call `POST /api/v1/multi-tenant/register/services` with `service_name`, `unit_type`, `price_per_unit`, `currency`, `is_active`. |
| 4 | Retry your inference request. |

For full setup steps, see the [Setup Guide](SETUP_GUIDE.md). For other issues, see the [Troubleshooting Guide](TROUBLESHOOTING.md).
