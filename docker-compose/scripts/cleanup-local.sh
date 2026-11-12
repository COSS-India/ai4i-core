#!/usr/bin/env bash
#
# Tear down the full local stack: host apps, NMT container, Compose containers + volumes.
# Does NOT rebuild anything. Run setup-local.sh afterwards for a fresh install.
#
# Usage (host terminal where Docker works):
#   export AI4I_LOCAL=/path/to/cloned-repos   # parent of ai4i-core/
#   bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/cleanup-local.sh"
#
# Optional:
#   REMOVE_HF_CACHE=1   also delete the Docker volume hf-cache (forces re-download of IndicTrans2)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$(cd "${SCRIPT_DIR}/.." && pwd)"
CORE="$(cd "${COMPOSE}/.." && pwd)"
AI4I_LOCAL="${AI4I_LOCAL:-$(cd "${CORE}/.." && pwd)}"
LOG_DIR="${COMPOSE}/.local-run-logs"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

need docker
docker info >/dev/null 2>&1 || die "Docker daemon not reachable (docker info failed)"
[ -f "${COMPOSE}/docker-compose.yml" ] || die "missing ${COMPOSE}/docker-compose.yml"

echo "=== Cleanup local AI4I stack ==="
echo "CORE=${CORE}"
echo "COMPOSE=${COMPOSE}"
echo

########################################
# 1) Stop host application processes
########################################
echo "=== 1) Stop host apps (uvicorn / Next.js) ==="
if [ -d "${LOG_DIR}" ]; then
  for pidf in "${LOG_DIR}"/*.pid; do
    [ -f "${pidf}" ] || continue
    pid="$(cat "${pidf}" 2>/dev/null || true)"
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
      echo "  kill ${pid} ($(basename "${pidf}"))"
      kill "${pid}" 2>/dev/null || true
    fi
    rm -f "${pidf}"
  done
fi
pkill -f "${CORE}/services/.*/.venv/bin/uvicorn" 2>/dev/null || true
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
pkill -f 'uvicorn main:app' 2>/dev/null || true
pkill -f 'python -m uvicorn' 2>/dev/null || true
# Next.js only if run from this repo's simple-ui
pkill -f "${CORE}/frontend/simple-ui" 2>/dev/null || true
sleep 1
echo "  host app stop attempted."

########################################
# 2) Remove NMT Triton container
########################################
echo "=== 2) Remove NMT container (indictrans) ==="
docker rm -f indictrans 2>/dev/null && echo "  removed indictrans" || echo "  indictrans not running"

########################################
# 3) Compose down + volumes
########################################
echo "=== 3) Docker Compose down -v (containers + volumes) ==="
cd "${COMPOSE}"
docker compose --profile monitoring --profile logging down -v
echo "  compose project removed (data volumes wiped)."

########################################
# 4) Optional HF model cache
########################################
if [ "${REMOVE_HF_CACHE:-}" = 1 ]; then
  echo "=== 4) Remove hf-cache volume ==="
  docker volume rm hf-cache 2>/dev/null && echo "  hf-cache removed" || echo "  hf-cache not present"
else
  echo "=== 4) Keeping Docker volume hf-cache (set REMOVE_HF_CACHE=1 to delete) ==="
fi

########################################
# 5) Local run logs
########################################
if [ -d "${LOG_DIR}" ]; then
  echo "=== 5) Clear ${LOG_DIR} ==="
  rm -rf "${LOG_DIR}"
fi

echo
echo "=== Cleanup complete ==="
echo "Nothing left to auto-start on reboot (no Compose containers)."
echo
echo "Next — fresh setup:"
echo "  export AI4I_LOCAL=${AI4I_LOCAL}"
echo "  export HF_TOKEN=hf_...   # required for NMT"
echo "  bash \"${COMPOSE}/scripts/setup-local.sh\""
