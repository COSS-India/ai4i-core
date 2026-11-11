#!/usr/bin/env bash
#
# Full local reset + setup through NMT E2E (SETUP-GUIDE.md).
# Run in a REAL host terminal (not an isolated agent sandbox) where Docker works:
#
#   export HF_TOKEN=hf_...          # required for gated IndicTrans2 download
#   export AI4I_LOCAL=/path/to/cloned-repos
#   # optional: NMT_SRC=/path/to/nmt-triton  (defaults searched below)
#   bash ai4i-core/docker-compose/scripts/reset-and-setup-local.sh
#
set -euo pipefail

AI4I_LOCAL="${AI4I_LOCAL:-/home/sagarkrishna/Desktop/OFFICE_DOCS/COSS/cloned-repos}"
CORE="${AI4I_LOCAL}/ai4i-core"
COMPOSE="${CORE}/docker-compose"
NMT_SERVICE_ID="${NMT_SERVICE_ID:-de9a4570f8c14f6859cb79c1934a4db9}"
LOG_DIR="${COMPOSE}/.local-run-logs"
mkdir -p "${LOG_DIR}"

die() { echo "ERROR: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

need docker
need python3.11
need curl
docker info >/dev/null 2>&1 || die "Docker daemon not reachable (docker info failed)"

[ -d "${COMPOSE}" ] || die "compose dir not found: ${COMPOSE} (symlink/copy pack into ai4i-core/docker-compose first)"
[ -f "${COMPOSE}/docker-compose.yml" ] || die "missing docker-compose.yml"

# Resolve nmt-triton source
resolve_nmt() {
  if [ -n "${NMT_SRC:-}" ] && [ -f "${NMT_SRC}/Dockerfile" ]; then
    echo "${NMT_SRC}"; return
  fi
  local c
  for c in \
    "${AI4I_LOCAL}/model-hosting/nmt-triton" \
    "${AI4I_LOCAL}/temp/local-setup-guide-try/model-hosting/nmt-triton" \
    "${AI4I_LOCAL}/temp/local-setup-guide-try/nmt-triton"
  do
    if [ -f "${c}/Dockerfile" ]; then echo "${c}"; return; fi
  done
  echo ""
}

NMT_SRC="$(resolve_nmt)"
[ -n "${NMT_SRC}" ] || die "nmt-triton not found. Clone model-hosting or set NMT_SRC="
[ -n "${HF_TOKEN:-}" ] || die "Set HF_TOKEN=hf_... (HuggingFace Read token with IndicTrans2 access)"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -n "${HOST_IP}" ] || HOST_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
[ -n "${HOST_IP}" ] || die "could not detect LAN IP for NMT endpoint (SSRF may block localhost)"

echo "=== Config ==="
echo "CORE=${CORE}"
echo "COMPOSE=${COMPOSE}"
echo "NMT_SRC=${NMT_SRC}"
echo "HOST_IP=${HOST_IP}  (NMT endpoint will be http://${HOST_IP}:8000)"
echo

########################################
# 1) Tear down
########################################
echo "=== 1) Tear down ==="
pkill -f 'uvicorn app.main:app' 2>/dev/null || true
pkill -f 'uvicorn main:app' 2>/dev/null || true
pkill -f 'next-server' 2>/dev/null || true
pkill -f 'next dev' 2>/dev/null || true
sleep 1
docker rm -f indictrans 2>/dev/null || true
cd "${COMPOSE}"
docker compose --profile monitoring --profile logging down -v
echo "Compose down complete."

########################################
# 2) Compose core
########################################
echo "=== 2) Compose core ==="
cp -n .env.example .env 2>/dev/null || true
docker compose up -d postgres redis
echo "Waiting for postgres/redis healthy..."
for i in $(seq 1 60); do
  pg=$(docker inspect -f '{{.State.Health.Status}}' ai4i-postgres 2>/dev/null || echo starting)
  rd=$(docker inspect -f '{{.State.Health.Status}}' ai4i-redis 2>/dev/null || echo starting)
  [ "${pg}" = healthy ] && [ "${rd}" = healthy ] && break
  sleep 2
done
docker compose ps
docker compose up -d kafka kafka-init etcd apisix
echo "Waiting for kafka/etcd/apisix healthy..."
for i in $(seq 1 90); do
  k=$(docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null || echo starting)
  e=$(docker inspect -f '{{.State.Health.Status}}' ai4i-etcd 2>/dev/null || echo starting)
  a=$(docker inspect -f '{{.State.Health.Status}}' ai4i-apisix 2>/dev/null || echo starting)
  [ "${k}" = healthy ] && [ "${e}" = healthy ] && [ "${a}" = healthy ] && break
  sleep 3
done
docker compose ps -a
docker compose ps -a | grep -q 'ai4i-kafka-init.*Exited (0)' || {
  # wait a bit more for init
  sleep 15
  docker compose ps -a | grep kafka-init || true
}

########################################
# 3) Env + migrations
########################################
echo "=== 3) setup-env + migrate ==="
# Prefer NMT endpoint in root env before regenerate (seed may pick it up on fresh migrate)
cd "${COMPOSE}"
./scripts/setup-env.sh
# Ensure TRITON_ENDPOINT_NMT is set for documentation / future seeds
if grep -q '^TRITON_ENDPOINT_NMT=' "${CORE}/.env" 2>/dev/null; then
  sed -i "s|^TRITON_ENDPOINT_NMT=.*|TRITON_ENDPOINT_NMT=http://${HOST_IP}:8000|" "${CORE}/.env"
else
  echo "TRITON_ENDPOINT_NMT=http://${HOST_IP}:8000" >> "${CORE}/.env"
fi

cd "${CORE}"
rm -rf .venv
python3.11 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r infrastructure/databases/requirements.txt
./scripts/migrate.sh all upgrade
deactivate

########################################
# 4) Start apps (background)
########################################
echo "=== 4) Start auth / platform-core / inference ==="
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

echo "Waiting for app HTTP..."
for i in $(seq 1 180); do
  a=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/docs || true)
  c=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8095/docs || true)
  h=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8090/health || true)
  [ "${a}" = 200 ] && [ "${c}" = 200 ] && [ "${h}" = 200 ] && break
  sleep 5
done
curl -s -o /dev/null -w "auth:%{http_code}\n" http://127.0.0.1:8081/docs
curl -s -o /dev/null -w "core:%{http_code}\n" http://127.0.0.1:8095/docs
curl -s http://127.0.0.1:8090/health || true
echo

########################################
# 5) NMT Triton
########################################
echo "=== 5) Build/run NMT Triton (long) ==="
cd "${NMT_SRC}"
if ! docker image inspect nmt-triton-cpu:latest >/dev/null 2>&1; then
  docker build -t nmt-triton-cpu .
else
  echo "Image nmt-triton-cpu:latest already present — skipping build (set FORCE_NMT_BUILD=1 to rebuild)"
  if [ "${FORCE_NMT_BUILD:-}" = 1 ]; then
    docker build -t nmt-triton-cpu .
  fi
fi

docker rm -f indictrans 2>/dev/null || true
docker run -d \
  -p 8000:8000 -p 8002:8002 \
  -v hf-cache:/cache \
  -e HF_TOKEN="${HF_TOKEN}" \
  --name indictrans \
  nmt-triton-cpu

echo "Waiting for Triton ready..."
for i in $(seq 1 120); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/v2/health/ready || true)
  [ "${code}" = 200 ] && break
  sleep 5
done
curl -s -o /dev/null -w "triton_ready:%{http_code}\n" http://127.0.0.1:8000/v2/health/ready

echo "Direct NMT infer (first call may download weights)..."
curl -s -X POST http://127.0.0.1:8000/v2/models/nmt/infer \
  -H "Content-Type: application/json" \
  -d '{"inputs":[
    {"name":"INPUT_TEXT","shape":[1,1],"datatype":"BYTES","data":["Hello, how are you?"]},
    {"name":"INPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["en"]},
    {"name":"OUTPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["hi"]}]}' \
  | tee "${LOG_DIR}/nmt-direct.json"
echo

########################################
# 6) Wire endpoint + platform NMT call
########################################
echo "=== 6) PATCH service endpoint + inference NMT ==="
NMT_ENDPOINT="http://${HOST_IP}:8000"
PATCH=$(curl -s -X PATCH http://127.0.0.1:8095/api/v1/services \
  -H "Content-Type: application/json" \
  -d "{\"services\":[{\"serviceId\":\"${NMT_SERVICE_ID}\",\"endpoint\":\"${NMT_ENDPOINT}\"}]}")
echo "PATCH response: ${PATCH}" | tee "${LOG_DIR}/nmt-patch.json"

# If localhost required as fallback when SSRF allows in this build:
if echo "${PATCH}" | grep -qiE 'error|fail|400|ssrf|private|loopback'; then
  echo "PATCH with LAN IP failed; trying http://127.0.0.1:8000 (may also be blocked)..."
  curl -s -X PATCH http://127.0.0.1:8095/api/v1/services \
    -H "Content-Type: application/json" \
    -d "{\"services\":[{\"serviceId\":\"${NMT_SERVICE_ID}\",\"endpoint\":\"http://127.0.0.1:8000\"}]}" \
    | tee "${LOG_DIR}/nmt-patch-fallback.json"
  echo
fi

TOKEN=$(curl -s -X POST http://127.0.0.1:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \
  | python3.11 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST http://127.0.0.1:8090/api/v1/nmt/inference \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "{
    \"input\": [{\"source\": \"Hello, how are you?\"}],
    \"config\": {
      \"serviceId\": \"${NMT_SERVICE_ID}\",
      \"language\": {\"sourceLanguage\": \"en\", \"targetLanguage\": \"hi\"}
    }
  }" | tee "${LOG_DIR}/nmt-via-inference.json"
echo
echo
echo "=== Done ==="
echo "Logs: ${LOG_DIR}"
echo "UI (optional): cd ${CORE}/frontend/simple-ui && npm install && npm run dev"
echo "Stop apps: kill \$(cat ${LOG_DIR}/*.pid)"
echo "Stop infra: cd ${COMPOSE} && docker compose --profile monitoring --profile logging down"
echo "Stop NMT: docker stop indictrans"
