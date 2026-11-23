# Minimal infra requirements — Docker Compose

Host sizing for [`docker-compose.yml`](docker-compose.yml). Application processes (auth, platform-core, inference, Simple UI) and model servers (e.g. NMT Triton from **`model-hosting/nmt-triton`**) run **outside** this compose unless you add them yourself.

Full walkthrough (order, migrate, NMT, UI): [SETUP-GUIDE.md](SETUP-GUIDE.md).

---

## 1. What you must run

| Mode | Compose command | Why |
|------|-----------------|-----|
| **App-minimal** | `docker compose up -d postgres redis` | **Postgres + Redis** — DBs/cache for host apps |
| **+ Monitoring (last)** | `docker compose --profile monitoring up -d` | App-minimal **plus** Prometheus / Grafana / Alertmanager / exporters |
| **+ Logging / optional tracing (last)** | `--profile logging` (+ Kafka if tracing) | See [§2.3](#23-full-compose-core--logging-optional-tracing-enabled) |
| **Interactive `setup-local.sh`** | choose mode 1–4 | Same options as §2.1–§2.4; confirms each step; optional NMT after apps |

**Local path:** uvicorn apps + Simple UI talk **directly** to `:8081` / `:8095` / `:8090`. **APISIX/etcd are not used locally** (production gateway only; still defined in `docker-compose.yml` but not started by the local guide/script).

| Component | Needed locally? |
|-----------|-----------------|
| **Postgres, Redis** | **Yes** — app-minimal |
| **Kafka** | **No** for basic APIs / NMT — optional for tracing / logging profile |
| **APISIX / etcd** | **No** — production gateway only |

NMT (`indictrans` on `:8000`) is **not** a Compose service — build/run separately (SETUP-GUIDE Step 9).

---

## 2. Hardware (host)

### 2.1 App-minimal = Compose (Postgres + Redis) + host apps

**Compose services required for host apps:**

| Compose service | Role |
|-----------------|------|
| `postgres` | App databases |
| `redis` | Cache |

```bash
docker compose up -d postgres redis
# wait until healthy, then setup-env → migrate → start uvicorn apps
```

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU (x86_64) | 4 vCPU |
| RAM | **4 GB** free (Compose + host apps) | **8 GB** |
| Disk | **10 GB** free | 20 GB SSD |
| OS | Linux + Docker Engine 24+ / Compose v2.20+ | same |
| GPU | Not required | — |

Host apps use **Python 3.11+** (optional Node 18+ for Simple UI) on top of the Docker budget above.

Approximate container budget (compose `deploy.resources` limits) for **app-minimal**:

| Service | CPU limit | Memory limit |
|---------|-----------|--------------|
| postgres | 0.80 | 1 Gi |
| redis | 0.40 | 512 Mi |
| **App-minimal total** | **~1.2 CPU** | **~1.5 Gi** |

### 2.2 Full Compose core + monitoring

**Means:** app-minimal (`postgres`, `redis`)  
**plus** `--profile monitoring`: `prometheus`, `grafana`, `alertmanager`, `node-exporter`, `kafka-exporter`.

> `kafka-exporter` expects Kafka. If you have not enabled optional tracing yet ([§2.3.2](#232-enable-optional-tracing--start-kafka)), either start Kafka or ignore exporter scrape failures.

```bash
docker compose up -d postgres redis
docker compose --profile monitoring up -d
```

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | **8 GB** free for Docker | **12 GB** |
| Disk | **30 GB** (Prometheus TSDB grows with retention) | 45 GB |

Default local retention is **15d** (`PROMETHEUS_RETENTION`). Increase only if you have disk headroom.

### 2.3 Full Compose core + logging (Optional Tracing enabled)

**Means:** app-minimal (`postgres`, `redis`)  
**plus** `--profile logging`: `opensearch`, `opensearch-dashboards`, `fluent-bit`  
**plus** optional Kafka when you enable tracing ([§2.3.2](#232-enable-optional-tracing--start-kafka)).

OpenSearch is the heavy piece (JVM `-Xms512m -Xmx768m` in this compose).

#### 2.3.1 Start the logging profile

```bash
sudo sysctl -w vm.max_map_count=262144   # once per host, for OpenSearch

docker compose --profile logging up -d
```

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | **12 GB** free for Docker (OpenSearch + logging stack) | **16 GB** |
| Disk | **40 GB** | 60 GB+ |
| `vm.max_map_count` | **≥ 262144** | required for OpenSearch |

Fluent Bit’s Kafka output and the OTEL trace path stay idle or retry until you enable Kafka below.

#### 2.3.2 Enable optional tracing — start Kafka

Kafka is **not** part of app-minimal. Start it when you want **optional tracing** (and so Fluent Bit / OTEL can use the log/trace bus):

```bash
# From docker-compose/
docker compose up -d kafka kafka-init

until [ "$(docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null)" = healthy ]; do
  sleep 3
done
docker compose ps -a
# Expect: ai4i-kafka Up (healthy); ai4i-kafka-init exited 0 (topics created)
```

| Kafka pieces | Role |
|--------------|------|
| `kafka` | Broker (host port `9092`) |
| `kafka-init` | One-shot topic create (incl. OTEL / logging topics) |
| Volume `kafka-data` | Persist broker data — keep `KAFKA_CLUSTER_ID` stable |

Approximate Kafka budget: **~1.0 CPU / ~1.5 Gi** (compose limits). Add this on top of §2.3.1 when tracing is enabled.

Without Kafka: host apps still run for basic APIs / NMT; you may see Kafka connection warnings. With Kafka: tracing consumers and Fluent Bit’s Kafka pipeline can run cleanly.

### 2.4 Full Compose core + monitoring + logging

**Means:** app-minimal + **Kafka (if tracing)** + monitoring profile + logging profile.

```bash
docker compose up -d postgres redis
# optional tracing: docker compose up -d kafka kafka-init
docker compose --profile monitoring --profile logging up -d
```

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 6 vCPU | 8+ vCPU |
| RAM | **16 GB** free for Docker | **24 GB** |
| Disk | **50 GB** SSD | 80 GB+ |

### 2.5 NMT Triton (only) — add-on to §2.1–§2.4

**Not a Compose tier.** CPU IndicTrans2 runs as a separate Docker container (`model-hosting/nmt-triton` → `indictrans` on `:8000`).

**Add these resources on top of whichever setup you chose** in §2.1–§2.4 (do not replace that baseline):

| Extra resource (NMT only) | Minimum add-on | Recommended add-on |
|---------------------------|----------------|--------------------|
| RAM | **+8 GB** | **+12 GB+** (translation is CPU/RAM heavy) |
| Disk | **+40 GB** | **+60 GB** (image ~18 GB + `hf-cache` weights) |
| CPU | **+2 vCPU** | **+4 vCPU** |
| GPU | Not required for CPU NMT path | — |

Also on the host (inference service, not Triton): first `pip install` may pull spaCy `en_core_web_lg` (~588 MB) — small vs the NMT image/cache above.

**Example:** §2.1 app-minimal (~4–8 GB) + this section → plan ~12–20 GB system RAM if NMT shares the host. §2.4 (~16–24 GB Docker) + NMT → prefer a larger machine or run Triton on a separate host.

Build/run steps: SETUP-GUIDE Part A.

---

## 3. Software prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Engine | 24+ | Compose + NMT container |
| Docker Compose | v2.20+ (`docker compose`) | Profiles + `deploy.resources` |
| Git | any recent | Clone `ai4i-core` + `model-hosting` |
| Python | **3.11+** (`python3.11` / `python3.12` / `python3`) | Host apps + migrations; PyPI `ai4i-core` requires `>=3.11` |
| Node.js | 18+ | Optional Simple UI |
| HuggingFace **Read** token | for Part A NMT | Gated IndicTrans2 weights (`HF_TOKEN`) |
| `curl` / `psql` | optional | Health checks |

Verify:

```bash
docker --version
docker compose version
docker ps
python3.11 --version || python3 --version   # must be 3.11+ (not 3.10)
```

---

## 4. Disk layout (volumes)

Named volumes under the Compose project (default `ai4i-infra`):

| Volume | Typical growth |
|--------|----------------|
| `postgres-data` | Low–medium (app DBs) — **app-minimal** |
| `redis-data` | Small (AOF/RDB) — **app-minimal** |
| `kafka-data` | Medium (7d topic retention) — **optional tracing / logging** ([§2.3](#23-full-compose-core--logging-optional-tracing-enabled)) |
| `prometheus-data` | Grows with scrape cardinality × retention |
| `opensearch-data` | Largest optional volume |

**Outside Compose (NMT):** Docker volume `hf-cache` persists IndicTrans2 downloads. Removed only if you pass `REMOVE_HF_CACHE=1` to `scripts/cleanup-local.sh`.

Wipe Compose volumes: `docker compose --profile monitoring --profile logging down -v` (or `scripts/cleanup-local.sh`).

---

## 5. Network / ports

Ensure these host ports are free for the mode you enable:

**App-minimal** (`postgres` / `redis`): `5432`, `6379`  
**Optional tracing / Kafka** ([§2.3](#23-full-compose-core--logging-optional-tracing-enabled)): `9092`  
**Monitoring:** `9090`, `9095`, `3001`, `9100`, `9308`  
**Logging:** `9200`, `9600`, `5601`  
**Host apps (outside Compose):** auth / platform-core / inference ports via `AUTH_SERVICE_PORT` / `PLATFORM_CORE_PORT` / `INFERENCE_SERVICE_PORT` in `docker-compose/.env` (defaults `8081` / `8095` / `8090`); Simple UI fixed `3000`  
**NMT Triton (outside Compose):** fixed `8000` (HTTP), `8002` (metrics); endpoint seeded as `TRITON_ENDPOINT_NMT` in repo-root `.env`

Do not run another compose stack (or a previous local run) that publishes the same ports. `setup-local.sh` refuses to continue if these listeners / `ai4i-*` / `indictrans` are already present — run `cleanup-local.sh` first.

---

## 6. Credentials (local defaults)

| Secret | Default |
|--------|---------|
| Postgres user / password | `postgres` / `postgres` |
| Postgres bootstrap DB | `ai4i_platform_db` |
| Extra DBs (init script) | `ai4iplatform_auth`, `ai4iplatform_core` |
| Redis password | `changeme` |
| Grafana | `admin` / `admin` |
| Seeded admin (after migrate) | `admin@ai4inclusion.org` / `ADMIN_PASSWORD` |

Change values in this pack’s `.env`; run `scripts/setup-env.sh` so ai4i-core service `.env` files stay in sync. For NMT E2E, set `TRITON_ENDPOINT_NMT` in the **repo-root** `.env` **before** migrations (see SETUP-GUIDE § C1b).

---

## 7. Smooth-run checklist

1. Linux host with enough free RAM for the chosen mode (§2.1–§2.4); if NMT shares the host, **add** §2.5 on top.
2. Docker Compose v2; copy `.env.example` → `.env`.
3. Start **app-minimal** (`postgres`, `redis`); wait until healthy.
4. Run `./scripts/setup-env.sh`; set `TRITON_ENDPOINT_NMT` if doing NMT; migrate auth → platform_db → `ai4iplatform_core upgrade heads` (SETUP-GUIDE § C3).
5. Start host apps (auth → platform-core → inference); optional Simple UI with `ENABLED_TASK_TYPES=llm,nmt`.
6. For **logging**: set `vm.max_map_count=262144`, then `--profile logging` ([§2.3.1](#231-start-the-logging-profile)). For **optional tracing**: start Kafka ([§2.3.2](#232-enable-optional-tracing--start-kafka)).
7. Enable monitoring only when needed — more RAM than §2.1.
8. If you use Kafka, keep `CLUSTER_ID` / `KAFKA_CLUSTER_ID` stable for the life of `kafka-data`.
9. If Fluent Bit cannot read container logs, adjust the Docker data-root bind mount in `docker-compose.yml` (Snap Docker uses a different path).
