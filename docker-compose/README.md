# Docker Compose — AI4I local platform infra

Local **platform infrastructure** for ai4i-core (Postgres, Redis, optional Kafka for tracing/logging, plus optional monitoring and logging). Application services (auth, platform-core, inference, Simple UI) run **natively on the host** and talk to each other directly — **no APISIX/etcd in the local path** (those are for production).

| Doc | Use when |
|-----|----------|
| **[SETUP-GUIDE.md](SETUP-GUIDE.md)** | Full walkthrough: NMT (`model-hosting`), Compose, env/migrations, apps, UI |
| **[MINIMAL-INFRA-REQUIREMENTS.md](MINIMAL-INFRA-REQUIREMENTS.md)** | Host CPU / RAM / disk by compose mode |
| **[scripts/README.md](scripts/README.md)** | `setup-env` / `cleanup-local` / `setup-local` usage |
| This README | Quick reference (tiers, images, ports) |

Path in the repo: **`ai4i-core/docker-compose/`**.

### Local NMT (separate repo)

NMT is **not** part of this Compose file. For the simple local translation E2E, clone
[`COSS-India/model-hosting`](https://github.com/COSS-India/model-hosting) (`feat/nmt-local-setup`)
next to `ai4i-core` and use **`nmt-triton/`** — see [SETUP-GUIDE Part A](SETUP-GUIDE.md#part-a--local-nmt-triton)
and [Part H](SETUP-GUIDE.md#part-h--verify-nmt-via-inference).

```bash
# sibling of ai4i-core
git clone -b feat/nmt-local-setup git@github.com:COSS-India/model-hosting.git
```

---

## Service tiers

| Tier | Compose | Services |
|------|---------|----------|
| **App-minimal** | `postgres redis` | DBs for host apps (local required) |
| **+ Kafka** | `kafka` (+ `kafka-init`) | Optional tracing / logging bus only |
| **Gateway (production only)** | `--profile gateway` | `etcd`, `apisix` — not used for local uvicorn/UI |
| **Monitoring (optional)** | `--profile monitoring` | `prometheus`, `alertmanager`, `grafana`, `node-exporter`, `kafka-exporter` |
| **Logging (optional)** | `--profile logging` | `opensearch`, `opensearch-dashboards`, `fluent-bit` |

---

## Image versions

| Component | Image |
|-----------|-------|
| PostgreSQL | `postgres:18.6-alpine` |
| Redis | `redis:8.10.3` |
| Kafka (KRaft) | `apache/kafka:4.3.1` |
| etcd | `quay.io/coreos/etcd:v3.5.9` |
| APISIX | `apache/apisix:3.7.0-debian` |
| Prometheus | `quay.io/prometheus/prometheus:v3.2.1` |
| Alertmanager | `quay.io/prometheus/alertmanager:v0.28.1` |
| Grafana | `grafana/grafana:11.6.0` |
| node-exporter | `prom/node-exporter:v1.7.0` |
| kafka-exporter | `danielqsj/kafka-exporter:v1.8.0` |
| OpenSearch | `opensearchproject/opensearch:2.11.0` |
| OpenSearch Dashboards | `opensearchproject/opensearch-dashboards:2.11.0` |
| Fluent Bit | `fluent/fluent-bit:2.2.0` |

---

## Quick start

```bash
cd docker-compose          # from the ai4i-core repo root
cp .env.example .env
# edit credentials if needed

# 1) App-minimal (required for host apps)
docker compose up -d postgres redis
# 2) Optional tracing — see MINIMAL-INFRA-REQUIREMENTS §2.3
# docker compose up -d kafka kafka-init
# Do NOT start etcd/apisix for local setup (production gateway only)

docker compose ps

# Optional LAST — after apps are verified
# docker compose --profile monitoring up -d
# docker compose --profile logging up -d
```

Defaults: `POSTGRES_USER/PASSWORD=postgres`, `REDIS_PASSWORD=changeme`, DB `ai4i_platform_db` (init also creates `ai4iplatform_auth`, `ai4iplatform_core`).

---

## Platform service environment files

Infra containers read **`docker-compose/.env`**.  
Host apps need per-service `.env` files under the repo. Generate them with:

```bash
cd docker-compose          # from the ai4i-core repo root
./scripts/setup-env.sh
```

`scripts/setup-env.sh` will:

1. Use the parent directory as the ai4i-core repo root  
2. Ensure the repo-root `.env` exists (from `env.template`)  
3. Sync Postgres/Redis/Kafka/branding from **docker-compose/.env** into the root `.env`  
4. Fill every `env.template` → service `.env` files (auth, platform-core, inference, Simple UI, Alembic, …)

For NMT E2E, set **`TRITON_ENDPOINT_NMT=http://127.0.0.1:8000`** in the **ai4i-core repo-root** `.env` **before** migrate (not in this Compose `.env`). Do not PATCH `/api/v1/services` (SSRF) — see [SETUP-GUIDE § C1b](SETUP-GUIDE.md#c1b-set-nmt-triton-endpoint-before-migrations-required-for-nmt-e2e).

Then from the **ai4i-core repo root** (core has dual Alembic heads — use `heads`, not `all upgrade`):

```bash
./scripts/migrate.sh ai4iplatform_auth upgrade
./scripts/migrate.sh ai4i_platform_db upgrade
./scripts/migrate.sh ai4iplatform_core upgrade heads
# start auth / platform-core / inference / UI (see SETUP-GUIDE.md Parts D–F)
```

Host apps use:

| Setting | Value |
|---------|--------|
| `POSTGRES_HOST` | `localhost` |
| `REDIS_HOST` | `localhost` |
| `KAFKA_SERVER` | `localhost:9092` |

---

## Ports

| Service | Host port | Notes |
|---------|-----------|--------|
| PostgreSQL | 5432 | |
| Redis | 6379 | |
| Kafka | 9092 | Host → EXTERNAL listener; containers use `kafka:9092` |
| etcd | 2379 | |
| APISIX HTTP | 9080 | |
| APISIX HTTPS | 9443 | |
| APISIX Admin | 9180 | key in `.env` / `config/apisix/config.yaml` |
| APISIX metrics | 9091 | |
| Prometheus | 9090 | profile `monitoring` |
| Alertmanager | 9095 | profile `monitoring` |
| Grafana | 3001 | avoids clash with Simple UI `:3000` |
| node-exporter | 9100 | |
| kafka-exporter | 9308 | |
| OpenSearch | 9200 | profile `logging` |
| OpenSearch Dashboards | 5601 | |

---

## Stop / reset

```bash
docker compose --profile monitoring --profile logging down      # keep volumes
docker compose --profile monitoring --profile logging down -v   # wipe data
```

---

## Layout

```
docker-compose/
├── docker-compose.yml
├── .env.example
├── README.md
├── SETUP-GUIDE.md                 # complete setup + architecture flow
├── MINIMAL-INFRA-REQUIREMENTS.md
├── config/                        # redis, apisix, prometheus, opensearch, …
└── scripts/
    ├── setup-env.sh               # generate ai4i-core per-service .env files
    ├── cleanup-local.sh           # tear down apps + Compose volumes + NMT
    ├── setup-local.sh             # fresh install; prints verify commands
    └── init-kafka-topics.sh       # used by kafka-init container
```
