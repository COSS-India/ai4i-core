# Docker Compose scripts

Helper scripts for the local pack under `ai4i-core/docker-compose/`.  
Full walkthrough: [../SETUP-GUIDE.md](../SETUP-GUIDE.md).

Run from a host terminal where Docker works. Set `AI4I_LOCAL` to the parent of `ai4i-core/` when using the cleanup/setup helpers.

| Script | Purpose |
|--------|---------|
| [`setup-env.sh`](setup-env.sh) | Sync Compose credentials into the repo-root `.env` and generate per-service `.env` files |
| [`cleanup-local.sh`](cleanup-local.sh) | Tear down local stack (host apps, NMT container, Compose `down -v`) |
| [`setup-local.sh`](setup-local.sh) | Fresh install: Compose → migrate → start apps + NMT; prints verify curls (does not wait/E2E) |
| [`init-kafka-topics.sh`](init-kafka-topics.sh) | Used by Compose `kafka-init` — creates default Kafka topics (not run by hand) |

---

## Typical flow

```bash
export AI4I_LOCAL=/path/to/cloned-repos   # parent of ai4i-core/

# 1) Wipe previous local stack (optional)
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"

# 2) Fresh setup (needs HF_TOKEN for NMT image/weights)
export HF_TOKEN=hf_...   # HuggingFace Read token
bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
```

Then run the verify commands printed by `setup-local.sh` (auth → platform-core → inference → Triton → NMT).

---

## Script details

### `setup-env.sh`

- **When:** After Compose `.env` exists and core infra is up (or before migrations).
- **Where:** `cd ai4i-core/docker-compose && ./scripts/setup-env.sh`
- **Also:** Repo root `./scripts/setup-env.sh` is a thin wrapper to this script.
- Sets `TRITON_ENDPOINT_NMT` yourself in **repo-root** `.env` **before** migrations if you need NMT E2E (see SETUP-GUIDE § C1b). `setup-local.sh` sets a default for you.
- Manual migrate (same as the guide / `setup-local.sh`):  
  `ai4iplatform_auth upgrade` → `ai4i_platform_db upgrade` → `ai4iplatform_core upgrade heads`.

### `cleanup-local.sh`

- Stops host uvicorn/Next processes started by setup, removes `indictrans`, runs  
  `docker compose --profile monitoring --profile logging down -v`.
- Optional: `REMOVE_HF_CACHE=1` to delete the Docker volume `hf-cache`.
- Does **not** start anything afterward.

### `setup-local.sh`

- Requires: Docker, `python3.11`, `curl`, `HF_TOKEN`, and `model-hosting/nmt-triton` (or `NMT_SRC=`).
- Optional: `FORCE_NMT_BUILD=1`, `TRITON_ENDPOINT_NMT=http://127.0.0.1:8000`.
- **Preflight:** if an existing stack is found (`ai4i-*` / `indictrans`, ports `8081`/`8095`/`8090`/`8000`, or setup PIDs), **exits** and tells you to run `cleanup-local.sh` first (does not clean up automatically).
- Writes `TRITON_ENDPOINT_NMT` into repo-root `.env` before migrate (no API PATCH).
- Starts apps in the background; logs under `docker-compose/.local-run-logs/`.
- Exits after printing manual verify steps — first inference `pip install` can still be running.

### `init-kafka-topics.sh`

- Invoked inside the `kafka-init` container by Compose. Do not run on the host unless you know the broker address and have the Kafka CLI.
