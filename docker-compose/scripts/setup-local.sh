#!/usr/bin/env bash
#
# Fresh local setup from scratch (Compose + migrations + apps + NMT container).
# Does NOT wait on health or run E2E curls — prints verify commands to run manually.
# Run AFTER cleanup-local.sh if you had a previous stack.
#
# Usage (host terminal where Docker works):
#   export AI4I_LOCAL=/path/to/cloned-repos
#   export HF_TOKEN=hf_...          # HuggingFace Read token (IndicTrans2)
#   # optional: NMT_SRC=/path/to/nmt-triton
#   # optional: FORCE_NMT_BUILD=1
#   # optional: TRITON_ENDPOINT_NMT=http://127.0.0.1:8000
#   bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$(cd "${SCRIPT_DIR}/.." && pwd)"
CORE="$(cd "${COMPOSE}/.." && pwd)"
AI4I_LOCAL="${AI4I_LOCAL:-$(cd "${CORE}/.." && pwd)}"
NMT_SERVICE_ID="${NMT_SERVICE_ID:-de9a4570f8c14f6859cb79c1934a4db9}"
LOG_DIR="${COMPOSE}/.local-run-logs"
mkdir -p "${LOG_DIR}"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

need docker
need python3.11
need curl
docker info >/dev/null 2>&1 || die "Docker daemon not reachable (docker info failed)"
[ -f "${COMPOSE}/docker-compose.yml" ] || die "missing ${COMPOSE}/docker-compose.yml"

resolve_nmt() {
  if [ -n "${NMT_SRC:-}" ] && [ -f "${NMT_SRC}/Dockerfile" ]; then
    echo "${NMT_SRC}"; return
  fi
  local c
  for c in \
    "${AI4I_LOCAL}/model-hosting/nmt-triton" \
    "${AI4I_LOCAL}/temp/local-setup-guide-try/model-hosting/nmt-triton"
  do
    if [ -f "${c}/Dockerfile" ]; then echo "${c}"; return; fi
  done
  echo ""
}

NMT_SRC="$(resolve_nmt)"
[ -n "${NMT_SRC}" ] || die "nmt-triton not found. Clone model-hosting or set NMT_SRC="
[ -n "${HF_TOKEN:-}" ] || die "Set HF_TOKEN=hf_... (HuggingFace Read token with IndicTrans2 access)"

# Seeded into mm_services at migrate time — do NOT PATCH /api/v1/services (SSRF blocks local hosts).
# Override with TRITON_ENDPOINT_NMT if Triton is on another reachable host.
NMT_ENDPOINT="${TRITON_ENDPOINT_NMT:-http://127.0.0.1:8000}"

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

stack_running() {
  # Compose / named containers from a previous local run
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qE '^ai4i-(postgres|redis|kafka|etcd|apisix|kafka-init)'; then
    return 0
  fi
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'indictrans'; then
    return 0
  fi
  # Host apps (or leftover listeners on platform ports)
  for port in 8081 8095 8090 8000; do
    if port_in_use "${port}"; then
      return 0
    fi
  done
  # PIDs recorded by a prior setup-local.sh
  if [ -d "${LOG_DIR}" ] && compgen -G "${LOG_DIR}/*.pid" >/dev/null 2>&1; then
    local pidf pid
    for pidf in "${LOG_DIR}"/*.pid; do
      pid="$(cat "${pidf}" 2>/dev/null || true)"
      if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        return 0
      fi
    done
  fi
  return 1
}

echo "=== Fresh setup ==="
echo "CORE=${CORE}"
echo "COMPOSE=${COMPOSE}"
echo "NMT_SRC=${NMT_SRC}"
echo "TRITON_ENDPOINT_NMT=${NMT_ENDPOINT}  (must be set in repo-root .env before migrate)"
echo

########################################
# 0) Refuse to continue if a local stack is already running
########################################
if stack_running; then
  cat >&2 <<EOF
ERROR: an existing local stack was detected on this machine
  (ai4i-* / indictrans containers, listeners on 8081/8095/8090/8000, and/or setup PIDs).

This script will NOT tear it down. For a fresh install, clean up first, then re-run setup:

  bash "${SCRIPT_DIR}/cleanup-local.sh"

  export HF_TOKEN=hf_...   # HuggingFace Read token
  bash "${SCRIPT_DIR}/setup-local.sh"
EOF
  exit 1
fi
echo "=== 0) No existing local stack detected — continuing ==="
echo

########################################
# 1) Compose core
########################################
echo "=== 1) Compose core ==="
cd "${COMPOSE}"
cp -n .env.example .env 2>/dev/null || true
docker compose up -d postgres redis
echo "Waiting for postgres/redis healthy..."
for _ in $(seq 1 60); do
  pg=$(docker inspect -f '{{.State.Health.Status}}' ai4i-postgres 2>/dev/null || echo starting)
  rd=$(docker inspect -f '{{.State.Health.Status}}' ai4i-redis 2>/dev/null || echo starting)
  [ "${pg}" = healthy ] && [ "${rd}" = healthy ] && break
  sleep 2
done
docker compose ps
docker compose up -d kafka kafka-init etcd apisix
echo "Waiting for kafka/etcd/apisix healthy..."
for _ in $(seq 1 90); do
  k=$(docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null || echo starting)
  e=$(docker inspect -f '{{.State.Health.Status}}' ai4i-etcd 2>/dev/null || echo starting)
  a=$(docker inspect -f '{{.State.Health.Status}}' ai4i-apisix 2>/dev/null || echo starting)
  [ "${k}" = healthy ] && [ "${e}" = healthy ] && [ "${a}" = healthy ] && break
  sleep 3
done
docker compose ps -a

########################################
# 2) Env + migrations
########################################
echo "=== 2) setup-env + migrate ==="
cd "${COMPOSE}"
./scripts/setup-env.sh
# Required before migrations so the NMT service seed gets a non-blank endpoint.
if grep -q '^TRITON_ENDPOINT_NMT=' "${CORE}/.env" 2>/dev/null; then
  sed -i "s|^TRITON_ENDPOINT_NMT=.*|TRITON_ENDPOINT_NMT=${NMT_ENDPOINT}|" "${CORE}/.env"
else
  echo "TRITON_ENDPOINT_NMT=${NMT_ENDPOINT}" >> "${CORE}/.env"
fi
grep '^TRITON_ENDPOINT_NMT=' "${CORE}/.env"

cd "${CORE}"
rm -rf .venv
python3.11 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r infrastructure/databases/requirements.txt
# auth + platform_db use a single head; core currently has two heads until the
# platform team lands a merge revision — use heads for core only.
./scripts/migrate.sh ai4iplatform_auth upgrade
./scripts/migrate.sh ai4i_platform_db upgrade
./scripts/migrate.sh ai4iplatform_core upgrade heads
deactivate

########################################
# 3) Start apps (background)
########################################
echo "=== 3) Start auth / platform-core / inference ==="
start_svc() {
  local dir="$1" port="$2" module="$3" log="$4"
  rm -rf "${dir}/.venv"
  (
    cd "${dir}"
    python3.11 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install -r requirements.txt
    exec python -m uvicorn "${module}" --host 0.0.0.0 --port "${port}" --reload
  ) >"${log}" 2>&1 &
  echo $! > "${log}.pid"
  echo "started ${dir} pid=$(cat "${log}.pid") log=${log}"
}

start_svc "${CORE}/services/auth-service" 8081 "app.main:app" "${LOG_DIR}/auth.log"
sleep 2
start_svc "${CORE}/services/platform-core-service" 8095 "app.main:app" "${LOG_DIR}/platform-core.log"
sleep 2
start_svc "${CORE}/services/inference-service" 8090 "main:app" "${LOG_DIR}/inference.log"

echo
echo "Apps started in background (first inference pip install may take several minutes — en_core_web_lg ~588 MB)."
echo "  auth log:       ${LOG_DIR}/auth.log"
echo "  platform-core:  ${LOG_DIR}/platform-core.log"
echo "  inference:      ${LOG_DIR}/inference.log"
echo

########################################
# 4) NMT Triton (start only — no wait / no auto-test)
########################################
echo "=== 4) Build/run NMT Triton ==="
cd "${NMT_SRC}"
if ! docker image inspect nmt-triton-cpu:latest >/dev/null 2>&1 || [ "${FORCE_NMT_BUILD:-}" = 1 ]; then
  docker build -t nmt-triton-cpu .
else
  echo "Image nmt-triton-cpu:latest already present — skipping build (FORCE_NMT_BUILD=1 to rebuild)"
fi

docker rm -f indictrans 2>/dev/null || true
docker run -d \
  -p 8000:8000 -p 8002:8002 \
  -v hf-cache:/cache \
  -e HF_TOKEN="${HF_TOKEN}" \
  --name indictrans \
  nmt-triton-cpu
echo "NMT container started (indictrans). First ready/infer may download weights into hf-cache."
echo

########################################
# 5) Print verify commands (run manually, one by one)
########################################
cat <<EOF
=== Setup complete (resources started) ===
Logs:     ${LOG_DIR}
Endpoint: TRITON_ENDPOINT_NMT=${NMT_ENDPOINT} (seeded at migrate; no PATCH)

Do NOT wait in this script — verify yourself when each layer is ready.
Run these one by one:

# 1) Auth
curl -s -o /dev/null -w "auth:%{http_code}\\n" http://127.0.0.1:8081/docs
# Expect: auth:200

# 2) Platform-core
curl -s -o /dev/null -w "core:%{http_code}\\n" http://127.0.0.1:8095/docs
# Expect: core:200

# 3) Inference (wait until first-time pip finishes)
#    Watch install/startup progress:
tail -f ${LOG_DIR}/inference.log
#    (Ctrl+C to stop following; look for "Application startup complete")
#    Then health-check:
curl -s http://127.0.0.1:8090/health
# Expect: healthy JSON / HTTP 200

# 4) Triton NMT ready
curl -s -o /dev/null -w "triton:%{http_code}\\n" http://127.0.0.1:8000/v2/health/ready
# Expect: triton:200

# 5) Direct Triton translate (first call may be slow while weights download)
curl -s -X POST http://127.0.0.1:8000/v2/models/nmt/infer \\
  -H "Content-Type: application/json" \\
  -d '{"inputs":[
    {"name":"INPUT_TEXT","shape":[1,1],"datatype":"BYTES","data":["Hello, how are you?"]},
    {"name":"INPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["en"]},
    {"name":"OUTPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["hi"]}]}'
# Expect: Hindi in outputs[].data

# 6) Login + NMT via inference API
TOKEN=\$(curl -s -X POST http://127.0.0.1:8081/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \\
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://127.0.0.1:8090/api/v1/nmt/inference \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$TOKEN" \\
  -d '{
    "input": [{"source": "Hello, how are you?"}],
    "config": {
      "serviceId": "${NMT_SERVICE_ID}",
      "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
    }
  }'
# Expect: output[].target with Hindi (e.g. नमस्ते, आप कैसे हैं?)

# Optional UI
# cd ${CORE}/frontend/simple-ui && npm install && npm run dev

# Cleanup later
# bash ${COMPOSE}/scripts/cleanup-local.sh
EOF
