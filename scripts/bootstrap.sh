#!/usr/bin/env bash
#
# AI4I Core — one-command developer bootstrap (the "gist" script).
#
# This is the canonical source for the published Gist. It takes a fresh machine
# from nothing to a running stack: it clones the repo (or updates an existing
# clone), installs any missing prerequisites, and runs ./scripts/dev/up.
#
# Default profile is "core" (backend only). See docs/SINGLE_COMMAND_SETUP.md.
#
# Usage (once published as a Gist):
#   curl -fsSL <GIST_RAW_URL> | bash                 # core profile, start immediately
#   curl -fsSL <GIST_RAW_URL> | bash -s -- frontend  # also bring up the UI
#   curl -fsSL <GIST_RAW_URL> | bash -s -- --prepare # clone + prereqs, DON'T start
#                                                    # (so you can set dev.secrets first)
#
# Optional overrides (env vars):
#   AI4I_REPO_URL    git URL to clone        (default: COSS-India/ai4i-core)
#   AI4I_BRANCH      branch to check out     (default: feature/gist-testing — see below)
#   AI4I_DIR         target directory        (default: ai4i-core-test — see below)
#   AI4I_PROFILE     profile if no arg given (default: core)
#   AI4I_SKIP_PREREQS=1   don't auto-install prerequisites
#   AI4I_NO_START=1       prepare only — don't run `up` (same as --prepare)
#   AI4I_*                DB/SMTP overrides are passed through to `up` (see dev.secrets.example)
#
set -euo pipefail

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

REPO_URL="${AI4I_REPO_URL:-https://github.com/COSS-India/ai4i-core.git}"
# TEMPORARY: the setup scripts currently live only on feature/gist-testing, and
# we clone into ai4i-core-test to avoid clobbering an existing ai4i-core checkout.
# Once merged, change BRANCH back to "master" and TARGET_DIR back to "ai4i-core".
BRANCH="${AI4I_BRANCH:-feature/gist-testing}"
TARGET_DIR="${AI4I_DIR:-ai4i-core-test}"
PROFILE="${AI4I_PROFILE:-core}"
NO_START="${AI4I_NO_START:-}"

# Args: an optional profile (positional) and/or --prepare / --no-start.
for arg in "$@"; do
    case "$arg" in
        --prepare|--no-start) NO_START=1 ;;
        --*) die "Unknown flag: $arg" ;;
        *)   PROFILE="$arg" ;;
    esac
done

# ── 1. Native Windows shells are unsupported — use WSL2 ───────────────────────
case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
        die "Native Windows shell detected. Run this inside WSL2 (see docs/SETUP_GUIDE.md § Windows)."
        ;;
esac

# ── 2. git is the only hard requirement to get started ───────────────────────
command -v git >/dev/null 2>&1 || die "git is required. Install git first, then re-run."

# ── 3. Clone fresh, or update an existing clone ──────────────────────────────
if [[ -d "$TARGET_DIR/.git" ]]; then
    say "Existing clone found at '$TARGET_DIR' — updating ($BRANCH)"
    git -C "$TARGET_DIR" fetch --quiet origin "$BRANCH"
    git -C "$TARGET_DIR" checkout --quiet "$BRANCH"
    git -C "$TARGET_DIR" pull --quiet --ff-only origin "$BRANCH" || \
        say "Could not fast-forward (local changes?) — continuing with the current checkout"
else
    say "Cloning $REPO_URL ($BRANCH) into '$TARGET_DIR'"
    git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# ── 4. Install prerequisites if any are missing ──────────────────────────────
needs_prereqs=false
for tool in docker python3.11; do
    command -v "$tool" >/dev/null 2>&1 || needs_prereqs=true
done
if [[ "$PROFILE" == "frontend" || "$PROFILE" == "all" ]]; then
    command -v node >/dev/null 2>&1 || needs_prereqs=true
fi

if [[ "$needs_prereqs" == "true" && -z "${AI4I_SKIP_PREREQS:-}" ]]; then
    say "Installing missing prerequisites (scripts/dev/install-prereqs.sh)"
    bash scripts/dev/install-prereqs.sh

    # Docker's unix group membership only applies to a new login session, so a
    # just-installed docker often isn't reachable in this same shell.
    if ! docker info >/dev/null 2>&1; then
        die "Docker was just installed but its daemon isn't reachable in this session.
Log out and back in (or run 'newgrp docker'), then finish with:
  cd $TARGET_DIR && ./scripts/dev/up $PROFILE"
    fi
fi

# ── 5a. Prepare-only mode — stop here so the dev can set secrets ─────────────
# This is the clean moment to provide credentials: create dev.secrets, fill it,
# then start the stack yourself. (Skip this entirely if random local passwords
# are fine — the normal flow below just works.)
if [[ -n "$NO_START" ]]; then
    if [[ ! -f dev.secrets && -f dev.secrets.example ]]; then
        cp dev.secrets.example dev.secrets
        say "Created dev.secrets from the template"
    fi
    cat <<EOF

Prepared '$TARGET_DIR' but did NOT start the stack (--prepare / AI4I_NO_START).

Next:
  1. cd $TARGET_DIR
  2. (optional) edit dev.secrets to set DB/Redis passwords and SMTP/SES creds
     — leave passwords blank to auto-generate local ones.
  3. ./scripts/dev/up $PROFILE

EOF
    exit 0
fi

# ── 5b. Bring up the stack ───────────────────────────────────────────────────
# `up` sources dev.secrets (if present) and AI4I_* env vars before generating
# the .env files, so any secrets are applied here.
say "Starting the stack (profile: $PROFILE)"
exec ./scripts/dev/up "$PROFILE"
