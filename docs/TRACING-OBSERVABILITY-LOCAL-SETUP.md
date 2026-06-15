# Tracing and Observability — Local Setup

Companion to [`END-TO-END-SETUP-GUIDE.md`](END-TO-END-SETUP-GUIDE.md). The minimal NMT path in that guide **does not require** this stack — inference works without Kafka. Use this document when you want traces, metrics, and dashboards locally.

**OS:** Linux only (same as the end-to-end guide).

---

## What the full stack adds

| Component | Role |
|-----------|------|
| **Kafka** | OTEL span transport from `inference-service` |
| **OpenSearch** | Trace and log storage |
| **Fluent Bit** | Kafka → OpenSearch pipeline |
| **Prometheus** | Metrics scrape and storage |
| **Grafana** | Dashboards |
| **Alertmanager** | Alert routing |
| **OpenSearch Dashboards** | Trace/log UI |

See [`docs/architecture/00-overview.md`](architecture/00-overview.md) for how the telemetry lane fits the platform.

---

## Start the observability stack

From the `ai4i-core` repo root (in addition to or instead of the minimal Part B3 services):

```bash
cd "$AI4I_LOCAL/ai4i-core"
docker compose -f docker-compose-local.yml up -d \
  postgres redis \
  zookeeper kafka \
  opensearch opensearch-init \
  prometheus alertmanager grafana node-exporter \
  fluent-bit opensearch-dashboards \
  nginx-gateway
```

Wait until core services are healthy:

```bash
docker compose -f docker-compose-local.yml ps
```

`postgres`, `redis`, and (if started) `kafka` / `opensearch` should be **healthy** before relying on tracing.

> This matches **Option B** in [`docs/SETUP_GUIDE.md`](SETUP_GUIDE.md#option-b-full-observability-stack-recommended).

---

## Typical local URLs

| UI / API | URL (defaults) |
|----------|----------------|
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| OpenSearch Dashboards | http://localhost:5601 |
| Alertmanager | http://localhost:9093 |

Credentials and overrides are in `docker-compose-local.yml` and root `.env` (`GRAFANA_*`, etc.).

---

## Application services

Keep running **auth** (`:8081`), **platform-core** (`:8095`), and **inference** (`:8090`) as in the end-to-end guide Part C.

Without Kafka, `inference-service` logs `KafkaConnectionError` and falls back — **NMT inference still works**. With Kafka up, spans export to the telemetry pipeline.

---

## Frontend (optional)

To view traces from Simple UI, set in `frontend/simple-ui/.env` (from `setup-env.sh`):

- `NEXT_PUBLIC_TELEMETRY_SERVICE_URL`
- `NEXT_PUBLIC_JAEGER_URL` (if your deployment exposes Jaeger; local stack may use OpenSearch Dashboards instead)

See `frontend/simple-ui/env.template` for defaults.

---

## Related documents

| Document | Location |
|----------|----------|
| End-to-end NMT setup (minimal infra) | `docs/END-TO-END-SETUP-GUIDE.md` |
| Full platform setup reference | `docs/SETUP_GUIDE.md` |
| Architecture overview | `docs/architecture/00-overview.md` |
| Inference telemetry path | `docs/architecture/03-inference-service.md` |
