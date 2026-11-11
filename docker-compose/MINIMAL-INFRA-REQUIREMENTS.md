# Minimal infra requirements — Docker Compose

Host sizing for [`docker-compose.yml`](docker-compose.yml). Application processes (auth, platform-core, inference, Simple UI) and model servers (e.g. NMT Triton) run **outside** this compose unless you add them yourself.

---

## 1. What you must run

| Mode | Compose command | Why |
|------|-----------------|-----|
| **1. Data stores** | `docker compose up -d postgres redis` | DBs/cache — start first; wait until healthy |
| **2. Messaging + gateway** | `docker compose up -d kafka kafka-init etcd apisix` | Required core before setup-env / apps |
| **Full core (both steps)** | `docker compose up -d` | Postgres, Redis, Kafka (KRaft), etcd, APISIX |
| **+ Monitoring (last)** | `--profile monitoring` | Prometheus / Grafana / Alertmanager / exporters |
| **+ Logging (last)** | `--profile logging` | OpenSearch / Dashboards / Fluent Bit |

---

## 2. Hardware (host)

### 2.1 App-minimal (Postgres + Redis only)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU (x86_64) | 4 vCPU |
| RAM | **4 GB** free for Docker + host apps | **8 GB** |
| Disk | **10 GB** free (images + volumes) | 20 GB |
| OS | Linux (Ubuntu tested) | same |
| GPU | Not required | — |

Host apps (Python 3.11+, optional Node 18+) need additional RAM beyond Docker.

### 2.2 Full core infra (default `docker compose up -d`)

Includes Kafka KRaft (~512–768 Mi heap), etcd, APISIX:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 vCPU | 6–8 vCPU |
| RAM | **8 GB** free for Docker | **12 GB** |
| Disk | **25 GB** free | 40 GB SSD |
| OS | Linux + Docker Engine 24+ / Compose v2.20+ | same |

Approximate container budget (compose `deploy.resources` limits):

| Service | CPU limit | Memory limit |
|---------|-----------|--------------|
| postgres | 0.80 | 1 Gi |
| redis | 0.40 | 512 Mi |
| kafka | 1.00 | 1536 Mi |
| etcd | 0.40 | 512 Mi |
| apisix | 0.40 | 512 Mi |
| **Core total (limits)** | **~3.0 CPU** | **~4 Gi** |

### 2.3 Core + monitoring

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | **10 GB** free for Docker | **14 GB** |
| Disk | **35 GB** (Prometheus TSDB grows with retention) | 50 GB |

Default local retention is **15d** (`PROMETHEUS_RETENTION`). Increase only if you have disk headroom.

### 2.4 Core + logging

OpenSearch is the heavy piece (JVM `-Xms512m -Xmx768m` in this compose):

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | **12 GB** free for Docker | **16 GB** |
| Disk | **40 GB** | 60 GB+ |
| `vm.max_map_count` | **≥ 262144** | required for OpenSearch |

```bash
# Linux — persist via /etc/sysctl.d if needed
sudo sysctl -w vm.max_map_count=262144
```

### 2.5 Full stack (core + monitoring + logging)

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 6 vCPU | 8+ vCPU |
| RAM | **16 GB** free for Docker | **24 GB** |
| Disk | **50 GB** SSD | 80 GB+ |

### 2.6 With NMT Triton on the same host

NMT image ~18 GB + model cache; translation is CPU-heavy:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | **16 GB** system | **24 GB+** |
| Disk | **50 GB+** free | 80 GB+ |
| GPU | Not required for CPU NMT path | — |

Prefer running NMT on a separate machine if the host is already at the full compose stack.

---

## 3. Software prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Engine | 24+ | Containers |
| Docker Compose | v2.20+ (`docker compose`) | Profiles + `deploy.resources` |
| Git | any recent | Clone repos |
| Python | **3.11+** (`python3.11`) | Host apps + migrations; PyPI `ai4i-core` requires `>=3.11` |
| Node.js | 18+ | Optional Simple UI |
| `curl` / `psql` | optional | Health checks |

Verify:

```bash
docker --version
docker compose version
docker ps
python3.11 --version   # must be 3.11.x+ (do not use system python3 if it is 3.10)
```

---

## 4. Disk layout (volumes)

Named volumes under the Compose project (default `ai4i-infra`):

| Volume | Typical growth |
|--------|----------------|
| `postgres-data` | Low–medium (app DBs) |
| `redis-data` | Small (AOF/RDB) |
| `kafka-data` | Medium (7d topic retention defaults) |
| `etcd-data` | Small |
| `prometheus-data` | Grows with scrape cardinality × retention |
| `opensearch-data` | Largest optional volume |

Wipe all: `docker compose --profile monitoring --profile logging down -v`.

---

## 5. Network / ports

Ensure these host ports are free for the mode you enable:

**Core:** `5432`, `6379`, `9092`, `2379`, `9080`, `9180`, `9443`, `9091`  
**Monitoring:** `9090`, `9095`, `3001`, `9100`, `9308`  
**Logging:** `9200`, `9600`, `5601`

Do not run another compose stack that publishes the same ports at the same time.

---

## 6. Credentials (local defaults)

| Secret | Default |
|--------|---------|
| Postgres user / password | `postgres` / `postgres` |
| Postgres bootstrap DB | `ai4i_platform_db` |
| Extra DBs (init script) | `ai4iplatform_auth`, `ai4iplatform_core` |
| Redis password | `changeme` |
| APISIX admin key | `edd1c9f034335f136f87ad84b625c8f1` |
| Grafana | `admin` / `admin` |

Change values in this pack’s `.env`; run `scripts/setup-env.sh` so ai4i-core service `.env` files stay in sync.

---

## 7. Smooth-run checklist

1. Linux host with enough free RAM for the chosen mode (see §2).
2. Docker Compose v2; copy `.env.example` → `.env`.
3. For logging: set `vm.max_map_count=262144` before OpenSearch.
4. Start **core** first; wait until healthy (`docker compose ps`).
5. Run `./scripts/setup-env.sh`, then ai4i-core migrations against `localhost:5432`.
6. Enable monitoring/logging only when needed — they use much more RAM than app-minimal.
7. Keep Kafka `CLUSTER_ID` / `KAFKA_CLUSTER_ID` stable for the life of `kafka-data`.
8. If Fluent Bit cannot read container logs, adjust the Docker data-root bind mount in `docker-compose.yml` (Snap Docker uses a different path).
