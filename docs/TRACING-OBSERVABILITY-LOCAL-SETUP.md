# Tracing and Observability — Local Setup

Companion to [`docker-compose/SETUP-GUIDE.md`](../docker-compose/SETUP-GUIDE.md). The core Compose path **does not require** the logging/monitoring profiles — inference works without OpenSearch. Use this document when you want traces, metrics, and dashboards locally.

**OS:** Linux only (same as the setup guide).

---

## What the full stack adds

| Component | Role | Compose |
|-----------|------|---------|
| **Kafka** | OTEL span transport from `inference-service` | **Core** (always on with `docker compose up -d`) |
| **OpenSearch** | Trace and log storage | `--profile logging` |
| **Fluent Bit** | Kafka → OpenSearch pipeline | `--profile logging` |
| **Prometheus** | Metrics scrape and storage | `--profile monitoring` |
| **Grafana** | Dashboards | `--profile monitoring` |
| **Alertmanager** | Alert routing | `--profile monitoring` |
| **OpenSearch Dashboards** | Trace/log UI | `--profile logging` |

See [`docs/architecture/00-overview.md`](architecture/00-overview.md) for how the telemetry lane fits the platform.

---

## Start the observability stack

From `ai4i-core/docker-compose/` (after core infra is up):

```bash
cd docker-compose
docker compose --profile monitoring --profile logging up -d
docker compose ps
```

`postgres`, `redis`, and `kafka` should be **healthy** before relying on tracing. OpenSearch may take a minute to become healthy.

---

## Typical local URLs

| UI / API | URL (defaults) |
|----------|----------------|
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |
| OpenSearch Dashboards | http://localhost:5601 |
| Alertmanager | http://localhost:9095 |

Credentials and overrides are in `docker-compose/.env` (`GRAFANA_*`, etc.). See [`docker-compose/README.md`](../docker-compose/README.md).

---

## Application services

Keep running **auth** (`:8081`), **platform-core** (`:8095`), and **inference** (`:8090`) as in the [setup guide Part C](../docker-compose/SETUP-GUIDE.md#part-c--application-services-one-by-one).

### Turn on trace export (required)

`KAFKA_ENABLED` defaults to `false` in `services/inference-service/.env`. While it's `false`, no spans reach Kafka and OpenSearch stays empty. Inference still works. Set it to `true` from the repo root:

```bash
sed -i 's/^KAFKA_ENABLED=.*/KAFKA_ENABLED=true/' services/inference-service/.env
```

Also ensure `KAFKA_SERVER=localhost:9092` (this Compose pack maps Kafka to **9092**, not 9093).

Restart inference-service (`--reload` doesn't pick up `.env` changes). It's working when the startup log shows `✓ Kafka span exporter initialized`. If it shows `Kafka span export disabled`, the flag is still `false`.

> Re-running `docker-compose/scripts/setup-env.sh` resets `KAFKA_ENABLED` to `false`, so set it again afterwards.

---

## Frontend (optional)

To view traces from Simple UI, set in `frontend/simple-ui/.env` (from `setup-env.sh`):

- `NEXT_PUBLIC_TELEMETRY_SERVICE_URL`

See `frontend/simple-ui/env.template` for defaults.

---

## Related documents

| Document | Link |
|----------|------|
| Canonical local setup | [docker-compose/SETUP-GUIDE.md](../docker-compose/SETUP-GUIDE.md) |
| Compose quick reference | [docker-compose/README.md](../docker-compose/README.md) |
| Architecture overview | [architecture/00-overview.md](architecture/00-overview.md) |
| Inference telemetry path | [architecture/03-inference-service.md](architecture/03-inference-service.md) |
