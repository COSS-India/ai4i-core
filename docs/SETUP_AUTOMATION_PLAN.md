# Setup Automation Plan

This document describes the shell-script setup automation that replaces the manual steps in [`SETUP_GUIDE.md`](SETUP_GUIDE.md), so a new contributor can go from `git clone` to a running stack with one command. The scripts described here are **implemented** under [`scripts/dev/`](../scripts/dev/).

---

## 1. Goal in one sentence

A new dev should be able to clone the repo and run a single command (e.g. `./scripts/dev/up frontend`) to get **postgres, redis, the three FastAPI services running natively under uvicorn, the simple-ui Next.js dev server, and the nginx gateway** all up and healthy — with sensible defaults filled in for the things they didn't pre-configure.

## 2. Hard constraints

These come from the team's existing decisions and shape the whole design:

| Constraint | Why it matters |
|---|---|
| **Infrastructure runs in Docker** (postgres, redis, kafka, zookeeper, prometheus, alertmanager, grafana, opensearch stack, fluent-bit, nginx-gateway) | The compose file already exists. We don't re-invent it. |
| **Application services run natively** (`auth-service`, `platform-core-service`, `inference-service`, `simple-ui`) | Hot reload via `uvicorn --reload` / `npm run dev`, ability to attach a debugger, faster iteration on `requirements.txt`. |
| **Primary OS targets: Linux, macOS, WSL2** (all bash) | One bash codebase covers ~95% of the team. |
| **Windows requires WSL2** | Already required by `SETUP_GUIDE.md`. We don't try to write a native PowerShell port. |
| **Application services keep `localhost` in their `.env`** | The `.env` files target the native-on-host flow. Containers reaching them go through `host.docker.internal:<port>` in `nginx.conf`. |

## 3. The user experience we're aiming for

```bash
git clone https://github.com/COSS-India/ai4i-core.git
cd ai4i-core
./scripts/dev/up frontend         # "core" is the default (backend only); pass "frontend" to also get the UI
```

When that command returns, the developer sees:

```
✓ Docker infra healthy (postgres, redis, nginx-gateway)
✓ Migrations applied
✓ auth-service on http://localhost:8081 (PID 12345, log: logs/auth.log)
✓ platform-core-service on http://localhost:8095 (PID 12346, log: logs/platform-core.log)
✓ inference-service on http://localhost:8090 (PID 12347, log: logs/inference.log)
✓ simple-ui on http://localhost:3000 (PID 12348, log: logs/simple-ui.log)

Open http://localhost:3000 to use the platform.
Admin login: admin@ai4inclusion.org / ADMIN_PASSWORD
Stop everything with: ./scripts/dev/down
```

That's the bar. Everything below is how we get there honestly.

## 4. Proposed file layout

We don't need one script per profile — that bloats fast. Instead, one orchestrator (`up`) takes a profile name, and small focused helpers do one job each. Linux/macOS/WSL share the bash files; Windows enters via WSL.

```
scripts/
  dev/
    up                    # main entrypoint: ./scripts/dev/up [profile] [--pull]
    down                  # stop everything this session started ([--prune] also wipes volumes)
    restart               # re-apply env + bounce native services only ([profile|service] [--no-env])
    status                # show what's up/down + log paths
    logs                  # tail logs for one service or all
    reset                 # wipe everything (volumes, venv, .env files) — destructive, confirms
    install-prereqs.sh    # OS-agnostic prereq installer (apt / brew / apk)

  dev/lib/
    common.sh             # shared helpers: log(), ok(), die(), wait_for_port(), is_wsl(), track_started(), etc.
    profiles.sh           # translate a profile name → compose --profile flags + native service set
    prereqs.sh            # OS guard (refuse non-WSL Windows) + check docker / python3.11 / node18+ / git
    env-bootstrap.sh      # generate root .env (dev defaults) if missing, run scripts/setup-env.sh, toggle KAFKA_ENABLED
    venv.sh               # create ONE shared .venv at the repo root + single pip install of every backend's requirements.txt
    infra.sh              # `docker compose up` with the right --profile flags for the chosen profile
    health.sh             # profile-aware health waits (postgres/redis always; nginx/kafka/opensearch per profile; service /docs)
    migrate.sh            # run scripts/migrate.sh all upgrade under the shared venv (after postgres healthy)
    services.sh           # start each backend under uvicorn --reload in the background, write PID (idempotent)
    frontend.sh           # npm install + npm run dev for simple-ui in the background (idempotent)
    pids.sh               # write/read/check/kill PIDs under .run/<service>.pid (SIGTERM → 10s → SIGKILL)

scripts/
  setup-env.sh            # EXISTING — keep, called by env-bootstrap.sh
  migrate.sh              # EXISTING — keep, called by lib/migrate.sh
```

Notes on the layout:

- One orchestrator (`up`) — not five sibling scripts (`up-core.sh`, `up-frontend.sh`, …). It takes a profile name; `profiles.sh` maps that name to the docker `--profile` flags and the native service set.
- Every helper under `lib/` is idempotent and re-runnable. The orchestrator calls them in order.
- Existing scripts (`scripts/setup-env.sh`, `scripts/migrate.sh`) are reused, not replaced. The new layer wraps them.
- Logs go to a tracked `logs/` directory; PIDs go to a tracked `.run/` directory. Both are gitignored.
- No `start.sh` / `stop.sh` at the repo root — keeping all dev tooling under `scripts/dev/` keeps the root clean.
- `health.sh` was split out from the orchestrator (it wasn't a named file in the original sketch) so health waits can be profile-aware without bloating `up`.
- `install-prereqs.sh` is a single OS-agnostic installer (detects apt / brew / apk), **not** a file per OS — see § 9 and the resolved note in § 12.

## 5. Profiles — what each one brings up

We mirror the docker-compose profile names so people who learn one mental model use it everywhere.

| Profile (`./scripts/dev/up <name>`) | Docker (infra) | Native (apps) | Observability / logging | Use when… |
|---|---|---|---|---|
| `core` *(default)* | postgres, redis | auth, platform-core, inference | Neither | You're a backend dev, no UI needed — **this is the default when no profile is given** |
| `frontend` | postgres, redis, nginx-gateway | auth, platform-core, inference, simple-ui | **Neither — explicitly excluded** | Everyday full-stack dev. The UI (`simple-ui`) is brought up only for the inference services. |
| `observability` | core + prometheus, alertmanager, grafana, node-exporter | same as core | Observability only | You're working on alerts / metrics dashboards |
| `logging` | core + opensearch ×3, fluent-bit, kafka, zookeeper | same as core | Logging only | You're working on the Logs Dashboard / trace ingestion |
| `all` | all of the above | all of the above | Both | You want the kitchen sink |

Implementation note: every profile builds on `core` (`observability`, `logging`, and `frontend` each add their own services on top of it; `all` is the union). Internally the orchestrator just translates a profile name into the right `docker compose --profile X --profile Y …` flags plus the set of native services to start. No duplicated logic. Because the layers are additive and every step is idempotent, profiles compose incrementally: after `./scripts/dev/up core` is already running, `./scripts/dev/up frontend` brings up **only** the remaining frontend services (`nginx-gateway` + `simple-ui`) and leaves the already-healthy core services untouched.

When `logging` (or `all`) is selected, `up` flips `KAFKA_ENABLED=true` in `services/inference-service/.env` before starting `inference-service`, then flips it back to `false` on `down` — so the inference-service trace exporter ships spans to Kafka while the logging stack is up, and silently degrades to stdout-only afterwards. (See the existing `KAFKA_ENABLED` plumbing in `services/inference-service/trace/setup.py`.)

## 6. What `./scripts/dev/up frontend` does, step by step

This is the contract. Every step prints one line and bails out loudly on failure.

1. **Detect environment** — bash version, OS, WSL flag. Refuse to run on non-WSL Windows with a clear message pointing at `SETUP_GUIDE.md § Windows (WSL)`.
2. **Check prerequisites** — docker (with `compose v2` subcommand), python3.11, node 18+, git. Print every missing one before exiting.
3. **Ensure root `.env`** — if `.env` is missing, copy from `env.template` and fill the credential placeholders. Credentials are **never hardcoded in this public repo**; they resolve in order: (1) `AI4I_*` env vars, (2) an untracked `dev.secrets` file (see `dev.secrets.example`) that `up` sources first, (3) a randomly-generated value for any password left unset (username defaults to `ai4i_user`). Whatever is resolved is written **once** into the gitignored `.env`, which drives both the dockerised postgres/redis and every service `.env` (via `setup-env.sh`) — one source of truth, so container and service credentials always match. **Never overwrite an existing `.env`.** If a postgres data volume already exists, warn that it may carry old credentials (postgres only applies them on first init).
4. **Generate service `.env` files** — call `scripts/setup-env.sh` (existing). Idempotent. Then `fill_smtp` substitutes the SMTP placeholders in the platform-core `.env` from `AI4I_SMTP_*` env vars (default empty) — **live SMTP/SES secrets are never committed; they're injected at runtime only**.
5. **Bring up Docker infra** — `docker compose -f docker-compose-local.yml [--profile frontend …] up -d`. `up` relies on compose's **default pull policy (`missing`)**: images already in the local cache are **never re-pulled**, and only absent images are fetched (so a first run still works). The explicit `./scripts/dev/up --pull` escape hatch adds `--pull always` to force a refresh. `docker compose up -d` is itself incremental: containers already running and healthy are left as-is, and only the services newly introduced by the selected profile are created. So running `up frontend` after `up core` starts just `nginx-gateway` and skips the already-up `postgres`/`redis`. Wait for postgres + redis (and kafka + opensearch if in profile) to report healthy. Hard cap of 180 seconds; on timeout, exit with a clear message.
6. **Create / update the shared `.venv`** —
   - Create `.venv` at the repo root if absent (`python3.11 -m venv .venv`).
   - `pip install -r services/auth-service/requirements.txt -r services/platform-core-service/requirements.txt -r services/inference-service/requirements.txt`. One pip invocation; pip's resolver picks a single version that satisfies all three lockfiles, and the shared deps (`fastapi`, `uvicorn`, `ai4icore-core`, `sqlalchemy`, `redis`, …) only get downloaded once. (`pip install` is itself idempotent — skips already-satisfied packages.)
   - If pip reports a dependency conflict, fail loudly — that means two services pin incompatible versions of the same library, which is a real bug to fix in `requirements.txt`, not something the script should paper over.
7. **Run migrations** — `./scripts/migrate.sh all upgrade` (existing). Only after postgres is healthy. Migrations run under the shared `.venv` as well.
8. **Start each backend service in the background** — for each of the three:
   - Source the shared `.venv/bin/activate` (or call `.venv/bin/python` directly).
   - `cd` into the service directory so `app.main:app` / `main:app` imports resolve.
   - `nohup python -m uvicorn …:app --host 0.0.0.0 --port <port> --reload > logs/<svc>.log 2>&1 &`
   - Write PID to `.run/<svc>.pid`.
   - Wait up to 30 s for `GET /health` (or the equivalent) to return 200; bail if it doesn't.
9. **(profile = frontend or all) Start simple-ui** — skipped if `simple-ui` is already up (its `.run/simple-ui.pid` points at a live process), so re-running `up frontend` after `up core` only fills in this one missing piece. Otherwise: `npm install` (idempotent — uses `package-lock.json`), then `nohup npm run dev > logs/simple-ui.log 2>&1 &`, PID to `.run/simple-ui.pid`. Wait for `GET /` to return 200. No API key step is needed — the UI talks to the inference services directly.
10. **Print the success banner** shown in § 3.

If any step fails, the script:
- Does **not** roll back containers (so the user can inspect them).
- Prints exactly which step failed and where to look.
- Exits non-zero so CI / wrapper scripts can detect it.

## 7. What `./scripts/dev/down` does

- Read every PID from `.run/*.pid`. Send `SIGTERM`; wait 10 s; `SIGKILL` survivors.
- Remove the PID files.
- `docker compose -f docker-compose-local.yml stop` (NOT `down` — we keep volumes so postgres data survives between runs).
- Print a summary: "stopped 4 native processes, 5 containers".

Optional flag: `--prune` runs `docker compose down -v` to also wipe volumes. Hidden behind a flag because it's destructive.

## 8. Hard problems and how we'll handle each

| Problem | Decision | Why |
|---|---|---|
| Long-running processes in a single script | **Background each app service with `nohup … &`**, track PIDs in `.run/`, redirect logs to `logs/`. | Foreground would require tmux/screen/foreman/honcho — extra dependency. Backgrounding is plain bash and survives terminal close. |
| User wants to see live logs | Provide `./scripts/dev/logs <service>` — wraps `tail -F logs/<svc>.log`. | Decouples "start everything" from "watch one thing". |
| A backgrounded service crashes silently | `./scripts/dev/status` probes each port. The success banner from `up` also reminds about `logs/`. | No process supervisor needed for v1. If this hurts in practice, we add one later. |
| Initial pip install is slow | **One shared `.venv` at the repo root**, populated by a single `pip install -r ... -r ... -r ...` invocation across all three services' `requirements.txt`. | Three separate venvs would each re-download the ~60 shared packages (`fastapi`, `uvicorn`, `ai4icore-core`, `sqlalchemy`, …). One shared venv downloads each package exactly once. Cold install drops from ~15 min to ~5. Trade-off: if two services pin incompatible versions of the same lib, pip fails fast — which we want, because that's a real bug. |
| Postgres has to be healthy before migrations | Bash `wait_for_port` helper that polls `docker compose exec postgres pg_isready` until success or 90 s timeout. | Same pattern auth-service's `depends_on: condition: service_healthy` uses, ported to bash. |
| User reruns `up` while services are already running, or runs a wider profile on top of a narrower one | Each step is idempotent and additive: venv create is skipped if `.venv` exists, pip install is no-op when packages are present, `docker compose up -d` no-ops for already-healthy containers and only creates the services the new profile adds, uvicorn/`simple-ui` start checks `.run/<svc>.pid` and re-uses it if the process is alive. So `up frontend` after `up core` only starts the missing `nginx-gateway` + `simple-ui`. | The "double-run" (and "I started core, now I want the UI too") are the most common new-dev flows; making them safe and incremental is non-negotiable. |
| User has `.env` files already configured | Never overwrite. `env-bootstrap.sh` only **creates** missing files; existing files are left alone. | Trashing customised dev secrets would be the worst possible footgun. |
| macOS Docker Desktop port quirks | Same as Windows/WSL — uses `host.docker.internal` and published ports. `nginx-gateway` already has the right `extra_hosts` entry. | Already works in the current manual flow; no special handling needed. |
| WSL2 inotify on `/mnt/c` doesn't fire for Windows-side edits | Document only — auto-reload works perfectly when the repo lives in WSL home (`~/ai4i-core`). The `SETUP_GUIDE.md § Windows (WSL)` already recommends this. | Setting `WATCHFILES_FORCE_POLLING=true` everywhere costs ~1% CPU; we don't impose that on users who keep the repo where it should be. |
| Cleanup on Ctrl-C mid-`up` | Trap `EXIT` in the script: kill any started PIDs, leave docker containers in whatever state they reached. | Half-started containers are fine to inspect; half-started python processes are not. |
| Per-OS bash incompatibilities | Stick to POSIX-portable bash (`#!/usr/bin/env bash`, no `declare -A` on macOS's stock bash 3.2, prefer `printf` over `echo -e`). | macOS users run a 2007 bash unless they `brew install bash`. We don't ask them to. |

## 9. Cross-OS strategy

**Bash, one codebase, runs everywhere we support:**

- **Linux**: native bash, no notes.
- **macOS**: native bash 3.2 — keep scripts in the POSIX subset; no associative arrays, no `mapfile`.
- **WSL2 (Windows)**: native bash inside WSL — same as Linux, with one extra check: refuse to run if `$WSL_DISTRO_NAME` is unset on Windows-looking systems. Hint the user to enter WSL first.

**What we do NOT build:**

- Native PowerShell port (`.ps1` files). Windows users go through WSL — that's the existing setup-guide policy, and a native port would be a maintenance tax for very little gain.
- `.bat` files for cmd.exe. Same reason.
- A docker-only fallback. The team has explicitly chosen native app services; we honor that.

If Windows-native ever becomes a hard requirement, the right move is a thin PowerShell launcher that calls `wsl.exe ./scripts/dev/up <profile>` — not a parallel codebase.

## 10. Inputs the user might want to override

All defaults can be overridden via environment variables, kept short and obvious:

| Variable | Default | What it does |
|---|---|---|
| `AI4I_PROFILE` | `core` | Same as the positional arg to `up`; arg wins. |
| `AI4I_POSTGRES_USER` | `ai4i_user` | Written into `.env` on first run only. |
| `AI4I_POSTGRES_PASSWORD` | _generated_ | If unset (and not in `dev.secrets`), a random password is generated on first run. Written to `.env` only. |
| `AI4I_REDIS_PASSWORD` | _generated_ | Same. |
| `AI4I_SMTP_AUTH_USERNAME` | unset → empty | SMTP/SES username injected into the platform-core `.env` (alert email). Not committed. |
| `AI4I_SMTP_AUTH_PASSWORD` | unset → empty | SMTP/SES password. Supply at runtime only — never hardcoded into the repo. |
| `AI4I_SMTP_SMARTHOST` | template default | Override the alert-email SMTP host:port. |
| `AI4I_SMTP_FROM` | template default | Override the alert-email From address. |
| `AI4I_SKIP_VENV` | unset | Skip step 6 (the shared venv create + pip install) — useful when only the docker layer changed. |
| `AI4I_SKIP_FRONTEND` | unset | Force-skip step 9 even on `frontend` profile. |
| `AI4I_LOGS_DIR` | `./logs` | Where backgrounded logs go. |

We deliberately **do not prompt interactively**. Unattended runs (CI, codespaces, devcontainers) matter, and a `read -p` in the middle is fatal there.

**Secrets never live in the repo.** No password or cloud credential is committed. DB/Redis passwords are supplied via `AI4I_*` env vars or an untracked `dev.secrets` file (copied from the committed, value-free `dev.secrets.example`), or randomly generated for local containers. Real cloud credentials (SMTP/SES) follow the same path and default to empty. Nothing sensitive reaches this public repository or the bootstrap gist; the generated `.env` files are gitignored.

## 11. What's explicitly out of scope (for v1)

- TLS / HTTPS termination.
- Cross-machine orchestration (e.g. infra on a shared host, apps on laptops).
- Process supervision (`systemd`, `launchd`, `pm2`) — backgrounding + PID files is enough for dev.
- Hot-reloadable secret rotation.
- Native Windows / PowerShell port (per § 9).
- Building production-ready container images for the application services — `Dockerfile`s exist but the team's decision is to run them natively in dev.
- Integration testing / smoke tests after `up` finishes. (`status` only checks port liveness, not contract.)

## 12. Open questions to resolve before implementation

1. **What does `status` show for a "running but unhealthy" service?** Currently PID liveness (native) + `docker ps` (containers). HTTP-level `/health` probing is still open.
2. **Logs rotation** — do we cap `logs/*.log` size or let them grow? Easiest: don't cap, document `./scripts/dev/down && rm -rf logs/`.

Resolved (no longer open):

- **No frontend API key bootstrap.** The simple-ui frontend does not require an admin-minted API key, so there is no key step to automate or document.
- **`up` never re-pulls images.** It relies on compose's default `missing` pull policy — cached images are never re-pulled, only absent ones are fetched; `./scripts/dev/up --pull` forces a refresh with `--pull always`.
- **Naming is `scripts/dev/up`** (with siblings `down` / `status` / `logs` / `reset`), not `scripts/up.sh` or `bin/ai4i`.
- **Per-OS prereqs: one OS-agnostic `scripts/dev/install-prereqs.sh`** that detects apt / brew / apk — not a file per OS (an earlier Ubuntu-only `scripts/bootstrap/ubuntu.sh` was replaced). Consistent with the § 9 "bash, one codebase" policy.
- **Node is only checked when the frontend will start.** A backend-only profile (`core`, `observability`, `logging`) doesn't require node/npm; `prereqs.sh` checks it only for `frontend`/`all` (or when `AI4I_SKIP_FRONTEND` is unset on those profiles).

## 13. Estimated effort

Roughly: one focused day for a strong bash author, two for someone refreshing on bash. Order of work:

1. `common.sh` + `prereqs.sh` (the foundation — 2 h).
2. `env-bootstrap.sh` + `infra.sh` (wrap existing stuff — 1 h).
3. `venv.sh` + `migrate.sh` (single shared-venv pip install + postgres-wait loop — 1.5 h).
4. `services.sh` + `pids.sh` + `frontend.sh` (the moving part — 3 h).
5. Orchestrator `up` / `down` / `status` / `logs` (gluing it together — 2 h).
6. Doc updates: rewrite `SETUP_GUIDE.md` § 4–9 to point at the new scripts, keep the manual steps as an appendix for debugging (2 h).

## 14. Success criteria

The plan delivers when:

- A teammate with a fresh laptop can `git clone … && cd … && ./scripts/dev/up frontend` and reach the Simple UI login within 5 minutes (warm docker images: under 2 min).
- Re-running `./scripts/dev/up frontend` on an already-up environment is a no-op (no errors, no double-starts, exits in under 5 s).
- `./scripts/dev/down` returns the machine to a clean state in under 30 s.
- The existing `SETUP_GUIDE.md` shrinks to "Run `./scripts/dev/up`. If anything fails, here's how to do it by hand:" + a debugging appendix.
- Linux / macOS / WSL2 contributors all use the same commands. Windows-native contributors are pointed at WSL.

---

**Status**: Design — awaiting team review and the decisions in § 12 before any code is written.
