# inference-service

Unified multi-task inference orchestration for **ai4i-core** — one `/inference` surface
over NMT, ASR, TTS, NER, OCR, transliteration, language/speaker diarization and
OpenAI-compatible LLM backends (Triton / LLM). Stateless: it resolves the target
`serviceId` via platform-core and emits OpenTelemetry trace spans to Kafka
(`kafka-topic-otel-trace`).

| | |
|---|---|
| **Port** | `8090` |
| **Stack** | FastAPI · Python 3.11 |
| **State** | stateless (Redis only for the service-resolution cache) |
| **Entrypoint** | `main.py` |

## Inference services

One unified endpoint `POST /api/v1/inference` (routed by `task_type`); each service is also a
per-service alias `POST /api/v1/{task}/inference`. LLM uses OpenAI-compatible
`POST /api/v1/chat/completions`. `GET /api/v1/inference/tasks` lists what is registered.

`NMT` · `ASR` · `TTS` · `NER` · `OCR` · `TRANSLITERATION` · `LANGUAGE_DETECTION` ·
`AUDIO_LANGUAGE_DETECTION` · `SPEAKER_DIARIZATION` · `LANGUAGE_DIARIZATION` · LLM chat

Registered in `orchestrator/task_service_registry.py`.

## Architecture

Full design, diagrams, and code-anchored detail live in the architecture docs:

- **[docs/architecture/03-inference-service.md](../../docs/architecture/03-inference-service.md)** — this service in depth: orchestration, per-task services, Triton/LLM routing, tracing.
- [docs/architecture/00-overview.md](../../docs/architecture/00-overview.md) — system overview (**start here**).

## Run

Runs **natively on the host** (not a `docker-compose-local.yml` service); other services
reach it via `inference-service:host-gateway`. Infrastructure (Redis, Kafka, OpenSearch, …)
still comes from compose at the repo root.

```bash
pip install -r requirements.txt
python main.py        # binds HOST:PORT from .env (default 0.0.0.0:8090)
```

Container image: see [`Dockerfile`](./Dockerfile) — `ENTRYPOINT ["python", "main.py"]`, `EXPOSE 8090`.
