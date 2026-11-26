# Docker Compose scripts

Helper scripts for the local pack under `ai4i-core/docker-compose/`.  
Full walkthrough: [../SETUP-GUIDE.md](../SETUP-GUIDE.md).

Run from a host terminal where Docker works. Set `AI4I_LOCAL` to the parent of `ai4i-core/` when using the cleanup/setup helpers.

| Script | Purpose |
|--------|---------|
| [`setup-env.sh`](setup-env.sh) | Sync Compose credentials into the repo-root `.env` and generate per-service `.env` files |
| [`cleanup-local.sh`](cleanup-local.sh) | Tear down local stack (host apps, NMT container, Compose `down -v`) |
| [`setup-local.sh`](setup-local.sh) | Interactive fresh install: choose mode (§2.1–§2.4) → confirm each step → apps → optional NMT |
| [`init-kafka-topics.sh`](init-kafka-topics.sh) | Used by Compose `kafka-init` — creates default Kafka topics (not run by hand) |

---

## Typical flow

```bash
export AI4I_LOCAL=/path/to/cloned-repos   # parent of ai4i-core/

# 1) Wipe previous local stack (optional)
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"

# 2) Interactive fresh setup (TTY required)
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
```

The script prompts for mode (app-minimal / +monitoring / +logging / both), confirms each step, then optionally **Simple UI**, then optionally **NMT Triton**. HuggingFace `HF_TOKEN` is requested only if you continue with NMT.

---

## Script details

### `setup-env.sh`

- **When:** After Compose `.env` exists and core infra is up (or before migrations).
- **Where:** `cd ai4i-core/docker-compose && ./scripts/setup-env.sh`
- **Also:** Repo root `./scripts/setup-env.sh` is a thin wrapper to this script.
- Set `TRITON_ENDPOINT_NMT` yourself in **repo-root** `.env` **before** migrations if you need NMT E2E (see SETUP-GUIDE Step 5). `setup-local.sh` sets a default for you.
- Manual migrate (same as the guide / `setup-local.sh`):  
  `ai4iplatform_auth upgrade` → `ai4i_platform_db upgrade` → `ai4iplatform_core upgrade heads`.

### `cleanup-local.sh`

- Stops host uvicorn/Next processes started by setup, removes `indictrans`, runs  
  `docker compose --profile monitoring --profile logging down -v`.
- Optional: `REMOVE_HF_CACHE=1` to delete the Docker volume `hf-cache`.
- Does **not** start anything afterward.

### `setup-local.sh`

- Requires: Docker, Python **3.11+** (`python3.11` / `3.12` / `python3`), `curl`, and an interactive terminal. Override with `PYTHON_BIN` if needed.
- **Modes:** (1) app-minimal (2) + monitoring (3) + logging / optional tracing (4) + monitoring + logging.
- Confirms each major step. Preflight exits if a stack is already present, or if any **host port** needed for the chosen mode is busy (prints PORT / SERVICE / ENV KEY / listener). Change the ENV KEY in `docker-compose/.env` and re-run (no need to free foreign services).
- Configurable uvicorn ports in `docker-compose/.env`: `AUTH_SERVICE_PORT`, `PLATFORM_CORE_PORT`, `INFERENCE_SERVICE_PORT`. UI stays `:3000`; NMT stays `:8000`/`:8002`.
- After the UI step: probes auth / platform-core / inference (+ UI if started) and prints status; if UI skipped, prints sample login curls; then asks about NMT.
- Seeds `TRITON_ENDPOINT_NMT` before migrate so NMT can be added later without PATCH.
- After apps: optional **Simple UI** (`npm` / `:3000`, sets `ENABLED_TASK_TYPES=llm,nmt`), then optional **NMT Triton** (`HF_TOKEN` / `NMT_SRC` only then). Optional: `FORCE_NMT_BUILD=1`.
- Logs under `docker-compose/.local-run-logs/`. Prints verify curls (does not wait/E2E).

### `init-kafka-topics.sh`

- Invoked inside the `kafka-init` container by Compose. Do not run on the host unless you know the broker address and have the Kafka CLI.
