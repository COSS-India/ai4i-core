# Docker Compose Local — Reference

Quick reference for [`docker-compose-local.yml`](../docker-compose-local.yml). See [`END-TO-END-SETUP-GUIDE.md`](END-TO-END-SETUP-GUIDE.md) (minimal) and [`TRACING-OBSERVABILITY-LOCAL-SETUP.md`](TRACING-OBSERVABILITY-LOCAL-SETUP.md) (full observability).

---

## What runs where

| In Docker | On the Linux host (native) |
|-----------|----------------------------|
| PostgreSQL, Redis | auth `:8081`, platform-core `:8095`, inference `:8090` |
| Kafka, OpenSearch, Fluent Bit, Prometheus, Grafana, etc. | Simple UI `:3000` (optional) |

App services are **not** started by compose by default — they run with uvicorn / `npm run dev` for hot-reload.

**Trace path (when enabled):** inference → Kafka (`localhost:9093`) → Fluent Bit → OpenSearch → OpenSearch Dashboards.

---

## Profiles

Only `postgres` and `redis` have no profile. Other services need their profile (auto-enabled when you name them on `up`).

| Profile | Services |
|---------|----------|
| *(none)* | `postgres`, `redis` |
| `logging` | `zookeeper`, `kafka`, `opensearch`, `opensearch-init`, `opensearch-dashboards`, `fluent-bit` |
| `observability` | `prometheus`, `alertmanager`, `grafana`, `node-exporter` |
| `streaming` | `zookeeper`, `kafka` |

---

## Environment

**Root `.env`** (from `env.template`) — read by Docker Compose:

| Variable | Used for |
|----------|----------|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Postgres container |
| `REDIS_PASSWORD` | Redis `requirepass` |
| `KAFKA_ADVERTISED_LISTENERS` | Kafka (default: `localhost:9093` + `kafka:29092` internal) |
| `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD` | Grafana login (default `admin` / `admin`) |

**`./scripts/setup-env.sh`** — copies values from root `.env` into per-service `.env` files (auth, platform-core, inference, frontend, Alembic). Host apps use `POSTGRES_HOST=localhost`, `REDIS_HOST=localhost`, `KAFKA_SERVER=localhost:9093`.

**Tracing:** set in `services/inference-service/.env`:

```bash
KAFKA_ENABLED=true
KAFKA_SERVER=localhost:9093
```

Restart inference after changing.

---

## Containers

All services use network `microservices-network` (`172.30.0.0/16`). From the **host**, use `localhost` + host port. **Inside Docker**, use service names (`postgres`, `kafka`, `opensearch`, …).

| Service | Container | Image | Profile | Host port | Env / config |
|---------|-----------|-------|---------|-----------|--------------|
| PostgreSQL | `ai4v-postgres` | `postgres:15-alpine` | — | `5432` | `${POSTGRES_*}` from root `.env` |
| Redis | `ai4v-redis` | `redis:7-alpine` | — | `6379` | `${REDIS_PASSWORD}`; config in `infrastructure/redis/` |
| Zookeeper | `ai4v-zookeeper` | `cp-zookeeper:7.4.0` | logging | *(internal)* | Fixed in compose |
| Kafka | `ai4v-kafka` | `cp-kafka:7.4.0` | logging | `9093` | `${KAFKA_ADVERTISED_LISTENERS}` |
| Prometheus | `ai4v-prometheus` | `prom/prometheus:latest` | observability | `9090` | `infrastructure/prometheus/prometheus.yml` |
| Alertmanager | `ai4v-alertmanager` | `alertmanager:v0.26.0` | observability | `9095` | `infrastructure/alertmanager/` |
| Grafana | `ai4v-grafana` | `grafana/grafana:latest` | observability | `3001` | `${GRAFANA_ADMIN_*}`; provisioning in `infrastructure/grafana/` |
| Node Exporter | `ai4v-node-exporter` | `node-exporter:v1.7.0` | observability | `9100` | Host `/proc`, `/sys` mounts |
| OpenSearch | `ai4v-opensearch` | `opensearch:2.11.0` | logging | `9204` | `infrastructure/opensearch/opensearch.yml` |
| OpenSearch init | `ai4v-opensearch-init` | `curlimages/curl` | logging | — | One-shot index template setup |
| OpenSearch Dashboards | `ai4v-opensearch-dashboards` | `opensearch-dashboards:2.11.0` | logging | `5602` | Points to `opensearch:9200` |
| Fluent Bit | `ai4v-fluent-bit` | `fluent/fluent-bit` | logging | — | `env_file: .env`; config in `infrastructure/fluent-bit/` |

**UIs:** Grafana http://localhost:3001 · Prometheus http://localhost:9090 · Alertmanager http://localhost:9095 · OpenSearch Dashboards http://localhost:5602

> Host **9093** = Kafka (not Alertmanager). Host **5602** = Dashboards (container uses 5601).

**Data:** named volumes (`postgres-data`, `redis-data`, `kafka-data`, etc.) persist across restarts. Config is bind-mounted from `infrastructure/`.

---

## Start / stop

**Minimal:**

```bash
docker compose -f docker-compose-local.yml up -d postgres redis
```

**Full observability:**

```bash
docker compose -f docker-compose-local.yml up -d \
  postgres redis zookeeper kafka \
  opensearch opensearch-init \
  prometheus alertmanager grafana node-exporter \
  fluent-bit opensearch-dashboards
```

Re-listing already-running services (e.g. `postgres redis`) is safe.

```bash
docker compose -f docker-compose-local.yml ps      # health
docker compose -f docker-compose-local.yml down    # stop, keep data
docker compose -f docker-compose-local.yml down -v # stop, wipe volumes
```

---

## Related

| Document | Link |
|----------|------|
| End-to-end setup | [END-TO-END-SETUP-GUIDE.md](END-TO-END-SETUP-GUIDE.md) |
| Tracing setup | [TRACING-OBSERVABILITY-LOCAL-SETUP.md](TRACING-OBSERVABILITY-LOCAL-SETUP.md) |
| Compose file | [docker-compose-local.yml](../docker-compose-local.yml) |
| Root env template | [env.template](../env.template) |
