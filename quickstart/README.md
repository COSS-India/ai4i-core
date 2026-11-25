# AI4I-Orchestrator quick start

Run the whole platform locally with one Docker Compose command, register a
model, and send your first inference request. No GPU, no model download and no
provider key: a small sample model that echoes your prompt is included.

This is for exploring the platform. To change code with hot reload, use
[`scripts/dev/up`](../scripts/dev/up) instead (see
[docs/SINGLE_COMMAND_SETUP.md](../docs/SINGLE_COMMAND_SETUP.md)).

> **Local use only.** Every secret in [`quickstart.env`](quickstart.env) is a
> fixed, published value, and every port is bound to `127.0.0.1`. Never deploy
> this stack or reuse its settings anywhere reachable from another machine.

## Contents

1. [Prerequisites](#prerequisites)
2. [Start](#1-start)
3. [Sign in to the portal](#2-sign-in-to-the-portal)
4. [Register the sample model and send a request](#3-register-the-sample-model-and-send-a-request)
5. [Call the API with curl](#4-call-the-api-with-curl)
6. [Usage, metrics and logs](#5-usage-metrics-and-logs)
7. [Stop and clean up](#6-stop-and-clean-up)
8. [What is included, and what is not](#what-is-included-and-what-is-not)
9. [Troubleshooting](#troubleshooting)

## Prerequisites

1. Docker Engine 24+ with Docker Compose v2.20+ (Docker Desktop on macOS or
   Windows, inside WSL2 on Windows).
2. At least 6 GB of memory allocated to Docker (8 GB recommended) and about
   20 GB of free disk. The stack uses about 2.2 GB of memory when idle, and
   the images total about 13 GB.
3. `python3` (3.8 or newer, standard library only) and `curl`, for the API
   walkthrough only.
4. These host ports free: 8080 (portal and API), 9090 (Prometheus), 9200
   (OpenSearch), 24224 (log shipping). See [Ports](#ports-already-in-use) to
   change them.

## 1. Start

From the repository root:

```bash
docker compose -f quickstart/docker-compose.yml up -d
```

The command returns once the platform services are healthy and the gateway
has started. Then open **http://localhost:8080**.

How long it takes:

1. **With the images already on your machine: under a minute.** Measured at
   23 seconds from an empty database on an Apple Silicon laptop. This is every
   start after the first.
2. **First run: about 15 minutes, depending on your connection.** Release
   images are not published to a registry yet, so Compose tries to pull them,
   reports `denied`, and builds them from your checkout instead. That message
   is expected. If the build stops on a network timeout, run the same command
   again (see [Troubleshooting](#the-first-build-fails-with-read-timed-out-or-another-network-error)).

What happens on start:

1. Postgres and Redis start.
2. The `migrate` container creates the databases, runs every migration, seeds
   roles and permissions and the default admin, then exits.
3. Kafka starts and its topics are created.
4. auth-service, platform-core-service, inference-service, the pay-per-use
   consumer and the portal start.
5. The gateway starts last, on port 8080.

Check the state at any time:

```bash
docker compose -f quickstart/docker-compose.yml ps
```

`migrate`, `kafka-init` and `opensearch-init` show `Exited (0)` once their
work is done. That is expected.

## 2. Sign in to the portal

Open http://localhost:8080 and sign in:

| Field | Value |
|---|---|
| Email | `admin@ai4inclusion.org` |
| Password | `Admin@12345` |

This is the seeded platform administrator (Adopter Admin).

## 3. Register the sample model and send a request

The fastest way is the script, which does every step through the API and
prints what it did:

```bash
python3 quickstart/demo.py
```

It creates and activates a tier, registers the sample model, creates and
publishes a service for it, gives your institution the tier and a budget,
creates an application and an API key, and sends one chat request. It prints
the API key and a ready-made curl command at the end. Running it again reuses
everything it already created and only makes a new API key.

To do the same in the portal, follow the
[Adopter Admin guide](../docs/onboarding%20guide/ONBOARDING-ADOPTER-GUIDE.md)
with these values:

| Step | Value |
|---|---|
| Model task type | `llm` |
| Model endpoint (callback URL) | `http://mock-llm:8000` |
| Model name the server expects (`adapterConfig.model_name`) | `quickstart/echo-llm` |
| Service endpoint | `http://mock-llm:8000` |

The endpoint uses the container name because the platform calls the model
from inside the Docker network.

## 4. Call the API with curl

Everything goes through the gateway at `http://localhost:8080`.

Sign in and keep the token:

```bash
TOKEN=$(curl -s http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@ai4inclusion.org","password":"Admin@12345"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
```

List the registered services:

```bash
curl -s http://localhost:8080/api/v1/services -H "Authorization: Bearer $TOKEN"
```

Send a chat request with the API key that `demo.py` printed. The API is
OpenAI-compatible, and `model` is the service ID:

```bash
curl -s http://localhost:8080/api/v1/chat/completions \
  -H "Authorization: Bearer <your-api-key>" \
  -H 'Content-Type: application/json' \
  -d '{"model": "quickstart-echo-llm",
       "messages": [{"role": "user", "content": "Say hello in five words."}]}'
```

Add `"stream": true` to get server-sent events instead.

Each service's full API is in its OpenAPI document. The services are not
published on the host, so read it from inside the container, for example:

```bash
docker compose -f quickstart/docker-compose.yml exec platform-core-service \
  python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8095/openapi.json').read().decode())" > platform-core-openapi.json
```

Ports inside the network: auth-service 8081, platform-core-service 8095,
inference-service 8090.

## 5. Usage, metrics and logs

| What | Where |
|---|---|
| Usage Dashboard (requests, tokens, spend) | Portal, **Usage Dashboard**. A request shows up within about a minute |
| Prometheus | http://localhost:9090. inference-service is the scraped target, for example the query `up{job="ai4icore-enterprise"}` |
| Logs and traces in OpenSearch | http://localhost:9200, indices `logs-*` and `traces-*` |
| Container logs | `docker compose -f quickstart/docker-compose.yml logs -f inference-service` |
| Grafana and OpenSearch Dashboards (optional) | Start with `--profile extras`, then http://localhost:3001 (admin / admin) and http://localhost:5601 |

Search the logs from the command line:

```bash
curl -s 'http://localhost:9200/logs-*/_search?size=5&sort=@timestamp:desc&q=container_name:inference' \
  | python3 -m json.tool
```

Optional extras:

```bash
docker compose -f quickstart/docker-compose.yml --profile extras up -d
```

## 6. Stop and clean up

Stop, keeping your data:

```bash
docker compose -f quickstart/docker-compose.yml down
```

Stop and delete everything, including the database:

```bash
docker compose -f quickstart/docker-compose.yml --profile extras down -v
```

Also remove the images built on the first run:

```bash
docker compose -f quickstart/docker-compose.yml --profile extras down -v --rmi all
```

## What is included, and what is not

| Included | Why |
|---|---|
| Postgres, Redis | Required by auth-service and platform-core |
| auth-service, platform-core-service, inference-service | The platform |
| Portal (simple-ui) | The web UI |
| Gateway (nginx) | Validates tokens with auth-service and passes the caller's identity to the services, the role APISIX plays in production |
| Kafka (single node) and the pay-per-use consumer | Request metering for the Usage Dashboard |
| Prometheus | Metrics |
| OpenSearch and fluent-bit | Logs and traces |
| Sample model (`mock-llm`) | Lets you try inference offline |

Left out: Casebase, Alertmanager and alert emails, the notifications consumer,
the nightly jobs (pyjob), email delivery, APISIX, high availability and
Kubernetes. Without the nightly jobs, the Usage Dashboard shows today from raw
usage rows, and past days stay empty.

## Troubleshooting

### `error from registry: denied` on the first run

Expected. The images are not published yet, so Compose builds them from your
checkout. To pull published images later, set `AI4I_VERSION` to a release tag:

```bash
AI4I_VERSION=v2.12 docker compose -f quickstart/docker-compose.yml up -d
```

### The first build fails with `Read timed out` or another network error

The first run downloads Python and Node packages for six images at once, and a
slow connection can time out. Run the same command again: finished layers are
cached, so it resumes where it stopped.

### Ports already in use

Every published port can be changed with an environment variable:

```bash
QS_GATEWAY_PORT=18080 QS_PROMETHEUS_PORT=19090 QS_OPENSEARCH_PORT=19200 QS_FLUENT_PORT=24225 \
  docker compose -f quickstart/docker-compose.yml up -d
```

If you change `QS_GATEWAY_PORT`, use that port in the URLs above.

### A service is unhealthy or keeps restarting

```bash
docker compose -f quickstart/docker-compose.yml ps
docker compose -f quickstart/docker-compose.yml logs --tail 100 <service>
```

Common causes:

1. `migrate` failed: run `docker compose -f quickstart/docker-compose.yml logs migrate`.
   A database left over from an older checkout can disagree with the
   migrations. Delete it with `down -v` and start again.
2. Docker ran out of memory: containers exit with code 137. Give Docker more
   memory, or stop other containers.
3. OpenSearch exits on Linux with `max virtual memory areas vm.max_map_count
   [65530] is too low`: run `sudo sysctl -w vm.max_map_count=262144`.

### Code changes do not show up

Compose reuses the images it built. Rebuild after pulling new code:

```bash
docker compose -f quickstart/docker-compose.yml up -d --build
```

### `401 Authentication required` from the API

The token is missing or expired (tokens last 60 minutes). Sign in again. API
keys go in the same header: `Authorization: Bearer <api-key>`.
