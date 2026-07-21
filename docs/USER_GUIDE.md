# User Guide

This guide teaches end-users how to use the AI4I-Core platform: how to sign in, make
inference requests (translation, speech, and more), and use the Simple UI. It ends with an
FAQ.

For installing and running the platform, see the [README](../README.md) and
[SETUP_GUIDE](./SETUP_GUIDE.md). For the full API reference, use the live docs each service
serves at `/docs` (Swagger UI), `/redoc`, and `/openapi.json`.

## Who this guide is for

Anyone using a running AI4I-Core instance: developers calling the APIs directly, and users of
the Simple UI web interface. It assumes the platform is already deployed and reachable.

## Before you start

You need:
- The base URL of a running instance (locally, the Simple UI is at `http://localhost:3000`
  and inference-service at `http://localhost:8090`).
- Credentials (username and password), or an API key issued by your administrator.

## Authentication

Requests are authenticated in one of two ways:

- **Bearer token (JWT)** — obtained by logging in. The Simple UI uses this.
- **API key** — a long-lived key you set once and reuse.

### Get a bearer token

Log in against auth-service to receive an `access_token`:

```bash
curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"YOUR_PASSWORD","remember_me":false}'
```

The response includes `access_token` and `refresh_token`. Send the access token on
subsequent requests:

```
Authorization: Bearer <access_token>
```

### Set an API key in the Simple UI

1. Open any service page in the Simple UI.
2. Click the menu button in the top-right corner.
3. Select **Manage API Key**.
4. Enter your API key (minimum 20 characters) and click **Save**.

## Make an inference request (API)

All inference tasks share one endpoint `POST /api/v1/inference`, routed by `task_type`, with
per-task aliases like `/api/v1/nmt/inference`. The live list of what a running instance
supports is `GET /api/v1/inference/tasks`.

> The **first** request for a task may take 1 to 3 minutes while the model loads. Wait for
> the response before assuming failure.

### Translate text (NMT)

```bash
curl -s -X POST http://localhost:8090/api/v1/nmt/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "input": [{"source": "Hello, how are you?"}],
    "config": {
      "serviceId": "<serviceId>",
      "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
    }
  }'
```

Response:

```json
{
  "output": [{"source": "Hello, how are you?", "target": "नमस्ते, आप कैसे हैं?"}],
  "smr_response": null
}
```

Find a valid `serviceId` with `GET /api/v1/services?task_type=nmt` on platform-core-service.

### Other tasks

The request shape is the same, with a task-specific `config`. Examples:

- **Speech recognition (ASR)** — `POST /api/v1/asr/inference`, send base64 audio:
  ```json
  {"audio": [{"audioContent": "<base64>"}],
   "config": {"language": {"sourceLanguage": "en"}, "serviceId": "<serviceId>", "audioFormat": "wav", "samplingRate": 16000}}
  ```
- **Text-to-speech (TTS)** — `POST /api/v1/tts/inference`:
  ```json
  {"input": [{"source": "Hello world"}],
   "config": {"language": {"sourceLanguage": "en"}, "serviceId": "<serviceId>", "gender": "female", "samplingRate": 22050, "audioFormat": "wav"}}
  ```
- **LLM chat** — OpenAI-compatible `POST /api/v1/chat/completions`.
- Other tasks (NER, OCR, transliteration, language and audio-language detection, speaker and
  language diarization) follow the same pattern. See the README task table and each service's
  `/docs`.

## Use the Simple UI

The Simple UI is a web interface for the most common tasks. After setting your API key:

### Translation (NMT)
1. Go to the **NMT** page (`/nmt`).
2. Choose source and target languages (use swap to reverse).
3. Enter text (up to 512 characters) and click **Translate**.
4. Copy or swap the result; view translation statistics.

### Speech recognition (ASR)
1. Go to the **ASR** page (`/asr`).
2. Choose inference mode (REST or Streaming), language, and sample rate.
3. Record from the microphone or upload an audio file.
4. Read the transcript, word count, response time, and confidence; play back with the
   waveform view.

### Text-to-speech (TTS)
1. Go to the **TTS** page (`/tts`).
2. Choose language, gender, audio format, and sampling rate.
3. Enter text (up to 512 characters) and click **Generate Audio**.
4. Play and download the generated audio.

## FAQ

**Which languages are supported?**
The Simple UI covers 22+ Indic languages for ASR, TTS, and NMT. The exact set depends on the
models registered in your instance. Query `GET /api/v1/inference/tasks` and the service
registry for what is available.

**My first request is very slow or times out. Is something broken?**
Usually not. The first request for a task can take 1 to 3 minutes while the model loads or
downloads weights. Subsequent requests are fast.

**I get an authentication error.**
Confirm your bearer token is current (tokens expire; use the refresh token to get a new one)
or that your API key is set correctly (minimum 20 characters) in the Simple UI.

**An inference call returns an error even though I am authenticated.**
The service may be registered with a blank or wrong `endpoint`. Ask your administrator to
point it at a reachable model server (`PATCH /api/v1/services`; see
[SETUP_GUIDE](./SETUP_GUIDE.md), Step 10).

**Where is the full API reference?**
Each service serves live docs: Swagger UI at `/docs`, ReDoc at `/redoc`, raw spec at
`/openapi.json`.

**Where do I report a problem?**
Open an issue at [GitHub Issues](https://github.com/COSS-India/ai4i-core/issues).

## Related documentation

- [README](../README.md) — overview, architecture, quick start
- [SETUP_GUIDE](./SETUP_GUIDE.md) · [END-TO-END-SETUP-GUIDE](./END-TO-END-SETUP-GUIDE.md)
- [Simple UI README](../frontend/simple-ui/README.md) — UI features and configuration
