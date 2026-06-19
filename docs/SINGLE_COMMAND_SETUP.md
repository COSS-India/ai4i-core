# Single-Command Setup

Get AI4I Core running on a fresh machine with **one command**. It clones the
repo, installs anything that's missing, and brings up the **core** profile
(postgres, redis, and the auth / platform-core / inference backend services).

> Prefer to do it by hand or want the full manual walkthrough? See
> [SETUP_GUIDE.md](SETUP_GUIDE.md). For how the automation is designed, see
> [SETUP_AUTOMATION_PLAN.md](SETUP_AUTOMATION_PLAN.md).

> The bootstrap clones the **`release-2.2`** branch into an **`ai4i-core/`** directory
> by default. Override with `AI4I_BRANCH` / `AI4I_DIR` (placed before `bash`).

---

## TL;DR

```bash
curl -fsSL https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh | bash
```

That's it. When it finishes, the backend is up and healthy:

- Auth Service — http://localhost:8081/docs
- Platform Core — http://localhost:8095/docs
- Inference Service — http://localhost:8090/docs

Want the **UI** as well? Pass the `frontend` profile:

```bash
curl -fsSL https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh | bash -s -- frontend
```

> **Published gist:** https://gist.github.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81
> The raw URL above is unpinned, so it always serves the latest gist revision.
> The canonical source for that gist lives in this repo at
> [`scripts/bootstrap.sh`](../scripts/bootstrap.sh) — see
> [Publishing / updating the gist](#publishing--updating-the-gist) to keep them in sync.

---

## Prerequisites

The bootstrap script installs almost everything for you. You only need:

- **A Unix-like shell** — Linux, macOS, or **Windows via WSL2** (native
  PowerShell / cmd is not supported; open a WSL2 terminal first).
- **git** — the one tool that must already be present.
- **sudo access** — the prerequisite installer uses your OS package manager
  (apt / brew / apk) to install docker, python 3.11, and (for the frontend)
  node.

---

## What the one command does

| Step | Action |
|---|---|
| 1 | Refuses to run in a native Windows shell (points you to WSL2). |
| 2 | Checks that `git` is available. |
| 3 | Clones `COSS-India/ai4i-core` (or updates it if the folder already exists). |
| 4 | Installs any missing prerequisites via [`scripts/dev/install-prereqs.sh`](../scripts/dev/install-prereqs.sh) (skip with `AI4I_SKIP_PREREQS=1`). |
| 5 | Runs [`./scripts/dev/up core`](../scripts/dev/up) — Docker infra → migrations → backend services, all health-checked. |

The equivalent manual steps (what the gist automates) are:

```bash
git clone -b release-2.2 https://github.com/COSS-India/ai4i-core.git
cd ai4i-core
./scripts/dev/up core        # "core" is the default; pass "frontend" to also get the UI
```

> **Tip:** add `--prepare` (`… | bash -s -- --prepare`) to clone + install
> prerequisites but **stop before starting**, so you can set `dev.secrets` first.

---

## Options

Override behaviour with environment variables. **Put them before `bash`, not
before `curl`** — `VAR=x curl … | bash` would set the variable for `curl`, not
for the script:

```bash
# Clone into a specific directory / target a different branch
curl -fsSL https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh | AI4I_DIR=~/code/ai4i AI4I_BRANCH=release-2.2 bash

# I've already installed docker/python/node myself — skip the installer
curl -fsSL https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh | AI4I_SKIP_PREREQS=1 bash
```

| Variable | Default | Purpose |
|---|---|---|
| `AI4I_PROFILE` | `core` | Profile to bring up (or pass it positionally: `bash -s -- frontend`). |
| `AI4I_DIR` | `ai4i-core` | Directory to clone into. |
| `AI4I_BRANCH` | `release-2.2` | Branch to check out. |
| `AI4I_REPO_URL` | `https://github.com/COSS-India/ai4i-core.git` | Git URL to clone. |
| `AI4I_SKIP_PREREQS` | _unset_ | Set to `1` to skip the prerequisite installer. |

Profiles available to `up` (each builds on `core`): `core` (default),
`frontend`, `observability`, `logging`, `all`. See the table in
[SETUP_AUTOMATION_PLAN.md § 5](SETUP_AUTOMATION_PLAN.md#5-profiles--what-each-one-brings-up).

### Credentials (`dev.secrets`)

No passwords are committed to the repo. DB/Redis passwords are resolved from, in
order: `AI4I_*` env vars → an untracked `dev.secrets` file → a randomly generated
value (so the one-command flow always works).

**When do I set secrets?** Three options, depending on whether you need specific
values (most people don't — random local passwords are fine):

1. **Never (default).** Just run the one-liner. Random local DB/Redis passwords
   are generated and kept consistent. Nothing to do.

2. **Prepare first, then start** — the clean moment to set secrets when using the
   gist. It clones + installs prereqs + creates `dev.secrets`, then **stops**:

   ```bash
   curl -fsSL <gist> | bash -s -- --prepare   # clones, doesn't start
   cd ai4i-core
   # edit dev.secrets (set DB/Redis passwords and/or SMTP/SES creds)
   ./scripts/dev/up core
   ```

3. **Inline env vars** — one shot, no file (note: secrets land in shell history).
   The assignment goes before `bash`, not before `curl`:

   ```bash
   curl -fsSL <gist> | AI4I_SMTP_AUTH_PASSWORD=... bash
   ```

If you cloned manually (not via the gist), just `cp dev.secrets.example dev.secrets`,
edit it, and run `./scripts/dev/up core`.

`dev.secrets` is sourced by `up`, so its values flow into the gitignored `.env`
files that drive both the containers and the services. Real cloud secrets
(SMTP/SES) belong **only** here — never in `env.template` or any committed file.

### Inference model endpoints (Triton / LLM)

Actual inference requires reachable model servers (Triton, and an LLM upstream).
Their addresses are sensitive infra and are **not** committed. Set them in
`dev.secrets`:

- `TRITON_ENDPOINT_NMT`, `TRITON_ENDPOINT_ASR`, `TRITON_ENDPOINT_TTS`, … — the DB
  **seed migration reads these env vars** and writes them into
  `mm_services.endpoint`. They take effect when the seed runs, i.e. on a **fresh
  database** (first `up`). If your DB already exists, re-seed by resetting the
  volume: `./scripts/dev/down --prune` then `./scripts/dev/up core`.
- `AI4I_LLM_DEFAULT_ENDPOINT` — injected into `services/inference-service/.env`
  as `LLM_DEFAULT_ENDPOINT` (the inference-service's own LLM proxy upstream).

Without these, the platform still comes up; only the actual inference calls fail
(`UnsupportedProtocol` → 500), because there's no model server to reach.

---

## Day-to-day commands

All commands live under `scripts/dev/` and act on the clone you set up:

| Command | What it does |
|---|---|
| `./scripts/dev/up [profile] [--pull]` | Start/extend the stack. Idempotent — re-running only fills in what's missing. `--pull` refreshes Docker images. |
| `./scripts/dev/restart [profile\|service] [--no-env]` | Re-apply env (`dev.secrets` + `.env`) and bounce the **native** services only; Docker keeps running. `service` = `auth\|platform\|inference\|ui`. |
| `./scripts/dev/status` | Show native services (PID + log path) and Docker containers. |
| `./scripts/dev/logs [auth\|platform\|inference\|frontend\|all]` | Tail service logs. |
| `./scripts/dev/down [--prune]` | Stop everything (volumes kept). `--prune` also removes Docker volumes. |
| `./scripts/dev/reset` | Wipe volumes, the shared `.venv`, `.env` files, and logs (confirms first). |
| `./scripts/dev/install-prereqs.sh` | Install prerequisites (apt/brew/apk) — run manually if you skipped them. |

- **Changed `dev.secrets` or a config value?** Run `./scripts/dev/restart` (or
  `restart <service>`) — it regenerates the `.env` files and restarts the native
  services without bouncing Docker or re-running migrations. A bare `up` won't
  pick it up because it skips already-running services.
- **Add the UI later:** `./scripts/dev/up frontend` starts only the missing
  `nginx-gateway` + `simple-ui`.
- Re-running `up` on an already-up environment is safe — every step is idempotent.

---

## Troubleshooting

- **"Docker was just installed but its daemon isn't reachable."** Docker's group
  membership only applies to a new login session. Log out and back in (or run
  `newgrp docker`), then finish with `cd ai4i-core && ./scripts/dev/up core`.
- **Native Windows shell detected.** Open a **WSL2** terminal and run the
  command there. Keep the repo inside the WSL filesystem (e.g. `~/ai4i-core`)
  so file-watching / hot-reload works.
- **A service didn't come up.** Check its log: `./scripts/dev/logs auth`
  (or `platform` / `inference` / `frontend`).
- **Database / Redis auth errors ("password authentication failed").** Postgres
  only applies its credentials when it *first* initialises its data volume. If
  you previously ran the stack with different credentials, the old volume sticks
  around and won't match the generated `.env`. Reset the volume and re-run:
  `./scripts/dev/down --prune` (or `./scripts/dev/reset`), then `./scripts/dev/up core`.
- **Start over from scratch.** `./scripts/dev/reset` wipes volumes, the shared
  `.venv`, `.env` files, and logs (it asks for confirmation first).

### Optional: alert email (SMTP/SES)

Alert-notification email is **off by default** — no secrets are baked into the
repo. To enable it, pass your SMTP/SES credentials at runtime (they're written
only into the git-ignored `.env`, never committed):

```bash
AI4I_SMTP_AUTH_USERNAME=... AI4I_SMTP_AUTH_PASSWORD=... \
AI4I_SMTP_SMARTHOST=email-smtp.ap-south-1.amazonaws.com:587 \
AI4I_SMTP_FROM=alerts@your-domain.org \
./scripts/dev/up core
```

---

## Publishing / updating the gist

The script that the one-liner runs is kept in-repo at
[`scripts/bootstrap.sh`](../scripts/bootstrap.sh) so it can be reviewed and
versioned. To publish it as a Gist (or refresh an existing one) with the
[GitHub CLI](https://cli.github.com/):

```bash
# Update THIS gist after editing scripts/bootstrap.sh (keeps the raw URL stable)
gh gist edit fbaa8b89366887bb288c132199341d81 scripts/bootstrap.sh

# …or create a brand-new gist (you'd then update the raw URLs in this doc)
gh gist create scripts/bootstrap.sh --public --desc "AI4I Core one-command dev setup"
```

The unpinned raw URL
(`https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh`)
always serves the latest revision, so editing the gist in place needs no doc
changes. **Keep the gist in sync with [`scripts/bootstrap.sh`](../scripts/bootstrap.sh)** —
that file is the source of truth.

> ⚠️ Piping a remote script straight into `bash` runs arbitrary code. The gist
> is public and its source is this repo's `scripts/bootstrap.sh` — encourage
> developers to read it first (open the gist, or
> `curl -fsSL https://gist.githubusercontent.com/bharathi-tarento-7401/fbaa8b89366887bb288c132199341d81/raw/bootstrap.sh`)
> before running.
