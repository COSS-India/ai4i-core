#!/usr/bin/env bash
#
# Interactive fresh local setup (Compose mode → migrate → host apps → optional UI/NMT).
# After the UI step: probes auth/core/inference (+ UI if started) and prints status.
# If UI skipped: prints sample login API curls. Then asks about NMT.
# Run AFTER cleanup-local.sh if you had a previous stack.
#
# Usage (host terminal where Docker works):
#   export AI4I_LOCAL=/path/to/cloned-repos
#   bash "$AI4I_LOCAL/ai4i-core/docker-compose/scripts/setup-local.sh"
#
# Modes match MINIMAL-INFRA-REQUIREMENTS.md §2.1–§2.4.
# HF_TOKEN / NMT paths are asked only if you continue with NMT after base setup.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="$(cd "${SCRIPT_DIR}/.." && pwd)"
CORE="$(cd "${COMPOSE}/.." && pwd)"
AI4I_LOCAL="${AI4I_LOCAL:-$(cd "${CORE}/.." && pwd)}"
NMT_SERVICE_ID="${NMT_SERVICE_ID:-de9a4570f8c14f6859cb79c1934a4db9}"
LOG_DIR="${COMPOSE}/.local-run-logs"
mkdir -p "${LOG_DIR}"

MODE=""
ENABLE_MONITORING=0
ENABLE_LOGGING=0
ENABLE_TRACING=0
STARTED_UI=0
STARTED_NMT=0

# Host uvicorn ports (overridden from docker-compose/.env via load_host_ports).
# Simple UI stays :3000; NMT publish stays 8000/8002 (seeded as TRITON_ENDPOINT_NMT).
AUTH_SERVICE_PORT=8081
PLATFORM_CORE_PORT=8095
INFERENCE_SERVICE_PORT=8090
NMT_ENDPOINT="${TRITON_ENDPOINT_NMT:-http://127.0.0.1:8000}"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

# Prefer PYTHON_BIN if set; else python3.11 → 3.12 → 3.13 → python3 (must be ≥3.11).
PYTHON_BIN="${PYTHON_BIN:-}"
resolve_python() {
  local cand ver major minor
  if [ -n "${PYTHON_BIN}" ]; then
    command -v "${PYTHON_BIN}" >/dev/null 2>&1 || die "PYTHON_BIN=${PYTHON_BIN} not found"
    cand="${PYTHON_BIN}"
  else
    for cand in python3.11 python3.12 python3.13 python3; do
      if command -v "${cand}" >/dev/null 2>&1; then
        break
      fi
      cand=""
    done
    [ -n "${cand}" ] || die "need Python 3.11+ (python3.11 / python3.12 / python3). Install python3.11 or set PYTHON_BIN."
  fi
  ver="$("${cand}" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
  major="${ver%%.*}"
  minor="${ver#*.}"
  if [ -z "${ver}" ] || [ "${major}" -lt 3 ] 2>/dev/null || { [ "${major}" -eq 3 ] && [ "${minor}" -lt 11 ]; }; then
    die "Python 3.11+ required (found ${cand} → ${ver:-unknown}). Install python3.11+ or set PYTHON_BIN."
  fi
  PYTHON_BIN="${cand}"
}

confirm() {
  local prompt="$1"
  local default="${2:-y}"
  local hint reply
  if [ "${default}" = y ]; then hint="Y/n"; else hint="y/N"; fi
  while true; do
    read -r -p "${prompt} [${hint}]: " reply || true
    reply="${reply:-$default}"
    case "${reply}" in
      y|Y|yes|YES) return 0 ;;
      n|N|no|NO) return 1 ;;
      *) echo "  Please answer y or n." ;;
    esac
  done
}

wait_healthy() {
  local name="$1"
  local attempts="${2:-60}"
  local sleep_s="${3:-2}"
  local i status
  echo "Waiting for ${name} healthy..."
  for i in $(seq 1 "${attempts}"); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "${name}" 2>/dev/null || echo starting)"
    [ "${status}" = healthy ] && return 0
    sleep "${sleep_s}"
  done
  echo "WARNING: ${name} not healthy yet (last=${status:-unknown}) — continuing; verify later."
}

resolve_nmt() {
  if [ -n "${NMT_SRC:-}" ] && [ -f "${NMT_SRC}/Dockerfile" ]; then
    echo "${NMT_SRC}"; return
  fi
  if [ -f "${AI4I_LOCAL}/model-hosting/nmt-triton/Dockerfile" ]; then
    echo "${AI4I_LOCAL}/model-hosting/nmt-triton"; return
  fi
  echo ""
}

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

# Who is listening on a host port (best-effort).
port_listener() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "sport = :${port}" 2>/dev/null | awk 'NR>1 {print; exit}'
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print}'
  else
    echo "(install ss or lsof to identify process)"
  fi
}

env_port() {
  local key="$1" default="$2" file="${COMPOSE}/.env"
  local val=""
  if [ -f "${file}" ]; then
    val="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '\r' || true)"
  fi
  if [ -z "${val}" ]; then
    echo "${default}"
  else
    echo "${val}"
  fi
}

ensure_compose_env() {
  cd "${COMPOSE}"
  cp -n .env.example .env 2>/dev/null || true
  # Merge any new keys from .env.example into an older .env (e.g. AUTH_SERVICE_PORT).
  if [ -f .env.example ] && [ -f .env ]; then
    local key
    while IFS= read -r key; do
      [ -n "${key}" ] || continue
      if ! grep -qE "^${key}=" .env 2>/dev/null; then
        grep -E "^${key}=" .env.example >> .env || true
      fi
    done < <(grep -E '^[A-Z0-9_]+=' .env.example | cut -d= -f1)
  fi
}

# Load AUTH_SERVICE_PORT / PLATFORM_CORE_PORT / INFERENCE_SERVICE_PORT from .env
load_host_ports() {
  ensure_compose_env
  AUTH_SERVICE_PORT="$(env_port AUTH_SERVICE_PORT 8081)"
  PLATFORM_CORE_PORT="$(env_port PLATFORM_CORE_PORT 8095)"
  INFERENCE_SERVICE_PORT="$(env_port INFERENCE_SERVICE_PORT 8090)"
  NMT_ENDPOINT="${TRITON_ENDPOINT_NMT:-http://127.0.0.1:8000}"
}

upsert_file_env() {
  local file="$1" key="$2" value="$3"
  [ -f "${file}" ] || return 0
  if grep -qE "^${key}=" "${file}" 2>/dev/null; then
    local escaped
    escaped="$(printf '%s' "${value}" | sed -e 's/[|&\\]/\\&/g')"
    # Portable in-place edit (GNU + BSD/macOS sed)
    sed -i.bak -e "s|^${key}=.*|${key}=${escaped}|" "${file}"
    rm -f "${file}.bak"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${file}"
  fi
}

# Keep Simple UI proxy URLs in sync with configured uvicorn ports (UI stays :3000).
sync_simple_ui_env_ports() {
  local ui_env="${CORE}/frontend/simple-ui/.env"
  [ -f "${ui_env}" ] || return 0
  upsert_file_env "${ui_env}" "AUTH_SERVICE_URL" "http://localhost:${AUTH_SERVICE_PORT}"
  upsert_file_env "${ui_env}" "PLATFORM_CORE_SERVICE_URL" "http://localhost:${PLATFORM_CORE_PORT}"
  upsert_file_env "${ui_env}" "INFERENCE_SERVICE_URL" "http://localhost:${INFERENCE_SERVICE_PORT}"
  upsert_file_env "${ui_env}" "API_URL" "http://localhost:3000"
}

# Align Prometheus host scrapes with AUTH/PLATFORM/INFERENCE ports (monitoring profile).
sync_prometheus_host_targets() {
  local prom="${COMPOSE}/config/prometheus/prometheus.yml"
  [ -f "${prom}" ] || return 0
  # Replace the three host.docker.internal:<port> lines under ai4i-host-services.
  "${PYTHON_BIN}" - "${prom}" "${AUTH_SERVICE_PORT}" "${INFERENCE_SERVICE_PORT}" "${PLATFORM_CORE_PORT}" <<'PY' || true
import pathlib, re, sys
path, auth, inf, core = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
text = path.read_text()
block = f"""      - targets:
          - host.docker.internal:{auth}
          - host.docker.internal:{inf}
          - host.docker.internal:{core}
"""
new, n = re.subn(
    r"      - targets:\n(?:          - host\.docker\.internal:\d+\n){3}",
    block,
    text,
    count=1,
)
if n:
    path.write_text(new)
PY
}

# Require all listed ports free. Args: "port|service label|ENV_KEY" (ENV_KEY optional)
require_ports_free() {
  local spec port rest label envkey busy=0
  echo
  echo "=== Host port preflight ==="
  printf "  %-8s %-28s %-24s %s\n" "PORT" "SERVICE" "ENV KEY" "STATUS"
  for spec in "$@"; do
    port="${spec%%|*}"
    rest="${spec#*|}"
    if [[ "${rest}" == *"|"* ]]; then
      label="${rest%%|*}"
      envkey="${rest#*|}"
    else
      label="${rest}"
      envkey="—"
    fi
    if port_in_use "${port}"; then
      printf "  %-8s %-28s %-24s BUSY — %s\n" "${port}" "${label}" "${envkey}" "$(port_listener "${port}")"
      busy=1
    else
      printf "  %-8s %-28s %-24s free\n" "${port}" "${label}" "${envkey}"
    fi
  done
  if [ "${busy}" = 1 ]; then
    cat >&2 <<EOF

ERROR: one or more host ports required for this setup are already in use.

You do NOT have to stop the other service. Edit the matching ENV KEY in:
  ${COMPOSE}/.env
then re-run this script (cleanup first if a previous AI4I stack is present).

Host apps:   AUTH_SERVICE_PORT  PLATFORM_CORE_PORT  INFERENCE_SERVICE_PORT
Compose:     POSTGRES_PORT REDIS_PORT KAFKA_EXTERNAL_PORT NODE_EXPORTER_PORT …
(Simple UI is fixed on :3000; NMT Triton publish is fixed on :8000/:8002.)

  bash "${SCRIPT_DIR}/cleanup-local.sh"   # only if wiping AI4I stack
  bash "${SCRIPT_DIR}/setup-local.sh"
EOF
    exit 1
  fi
  echo "=== All required ports are free ==="
  echo
}

# Ports for the selected mode (apps always included). UI/NMT checked when those steps run.
preflight_ports_for_mode() {
  local ports=()
  local p_pg p_redis p_kafka p_prom p_am p_graf p_node p_kexp p_os p_osp p_osd

  load_host_ports

  p_pg="$(env_port POSTGRES_PORT 5432)"
  p_redis="$(env_port REDIS_PORT 6379)"
  ports+=("${p_pg}|postgres|POSTGRES_PORT" "${p_redis}|redis|REDIS_PORT")
  ports+=("${AUTH_SERVICE_PORT}|auth-service (uvicorn)|AUTH_SERVICE_PORT")
  ports+=("${PLATFORM_CORE_PORT}|platform-core (uvicorn)|PLATFORM_CORE_PORT")
  ports+=("${INFERENCE_SERVICE_PORT}|inference (uvicorn)|INFERENCE_SERVICE_PORT")

  if [ "${ENABLE_TRACING}" = 1 ] || [ "${ENABLE_LOGGING}" = 1 ]; then
    p_kafka="$(env_port KAFKA_EXTERNAL_PORT 9092)"
    ports+=("${p_kafka}|kafka|KAFKA_EXTERNAL_PORT")
  fi
  if [ "${ENABLE_LOGGING}" = 1 ]; then
    p_os="$(env_port OPENSEARCH_PORT 9200)"
    p_osp="$(env_port OPENSEARCH_PERF_PORT 9600)"
    p_osd="$(env_port OPENSEARCH_DASHBOARDS_PORT 5601)"
    ports+=("${p_os}|opensearch|OPENSEARCH_PORT" "${p_osp}|opensearch perf|OPENSEARCH_PERF_PORT")
    ports+=("${p_osd}|opensearch-dashboards|OPENSEARCH_DASHBOARDS_PORT")
  fi
  if [ "${ENABLE_MONITORING}" = 1 ]; then
    p_prom="$(env_port PROMETHEUS_PORT 9090)"
    p_am="$(env_port ALERTMANAGER_PORT 9095)"
    p_graf="$(env_port GRAFANA_PORT 3001)"
    p_node="$(env_port NODE_EXPORTER_PORT 9100)"
    p_kexp="$(env_port KAFKA_EXPORTER_PORT 9308)"
    ports+=("${p_prom}|prometheus|PROMETHEUS_PORT" "${p_am}|alertmanager|ALERTMANAGER_PORT")
    ports+=("${p_graf}|grafana|GRAFANA_PORT" "${p_node}|node-exporter|NODE_EXPORTER_PORT")
    ports+=("${p_kexp}|kafka-exporter|KAFKA_EXPORTER_PORT")
  fi

  require_ports_free "${ports[@]}"
}

stack_running() {
  # Detect leftover AI4I resources only. Foreign listeners on the same ports are
  # handled by preflight (change *_PORT in .env) — do not treat them as our stack.
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qE '^ai4i-(postgres|redis|kafka|etcd|apisix|kafka-init|prometheus|grafana|opensearch)'; then
    return 0
  fi
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 'indictrans'; then
    return 0
  fi
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

mode_label() {
  case "$1" in
    1) echo "App-minimal = Compose (Postgres + Redis) + host apps" ;;
    2) echo "Full Compose core + monitoring" ;;
    3) echo "Full Compose core + logging (Optional Tracing enabled)" ;;
    4) echo "Full Compose core + monitoring + logging" ;;
    *) echo "unknown" ;;
  esac
}

select_mode() {
  cat <<EOF

=== Choose local setup mode ===
(See docker-compose/MINIMAL-INFRA-REQUIREMENTS.md §2)

  1) App-minimal = Compose (Postgres + Redis) + host apps
  2) Full Compose core + monitoring
  3) Full Compose core + logging (Optional Tracing enabled)
  4) Full Compose core + monitoring + logging

EOF
  local choice
  while true; do
    read -r -p "Enter mode [1-4]: " choice || true
    case "${choice}" in
      1|2|3|4) MODE="${choice}"; break ;;
      *) echo "  Enter 1, 2, 3, or 4." ;;
    esac
  done

  ENABLE_MONITORING=0
  ENABLE_LOGGING=0
  ENABLE_TRACING=0

  case "${MODE}" in
    1) ;;
    2) ENABLE_MONITORING=1 ;;
    3) ENABLE_LOGGING=1 ;;
    4) ENABLE_MONITORING=1; ENABLE_LOGGING=1 ;;
  esac

  echo
  echo "Selected: $(mode_label "${MODE}")"
  echo "(Local setup does not start APISIX/etcd — UI and curls talk to uvicorn directly.)"
  if [ "${ENABLE_LOGGING}" = 1 ]; then
    if confirm "Enable optional tracing (start Kafka + kafka-init)?" n; then
      ENABLE_TRACING=1
    else
      ENABLE_TRACING=0
      echo "  Skipping Kafka — logging profile will still start; Fluent Bit/OTEL may retry until Kafka is up."
    fi
  fi

  echo
  echo "Plan:"
  echo "  - Postgres + Redis (app-minimal)"
  [ "${ENABLE_TRACING}" = 1 ] && echo "  - Kafka + kafka-init (optional tracing)"
  [ "${ENABLE_MONITORING}" = 1 ] && echo "  - --profile monitoring"
  [ "${ENABLE_LOGGING}" = 1 ] && echo "  - --profile logging"
  echo "  - setup-env + migrate (seed TRITON_ENDPOINT_NMT for later NMT)"
  echo "  - Start auth / platform-core / inference"
  echo "  - Then ask whether to start Simple UI"
  echo "  - Then ask whether to start NMT Triton"
  echo
  confirm "Proceed with this plan?" y || { echo "Aborted."; exit 0; }
}

http_code() {
  # curl still prints %{http_code}=000 on connect fail but exits non-zero —
  # never append another 000 via || echo (that produced "000000").
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "$1" 2>/dev/null || true)"
  # strip stray CR/whitespace; default empty → 000
  code="$(printf '%s' "${code}" | tr -d '\r\n[:space:]')"
  echo "${code:-000}"
}

status_label() {
  local code="$1"
  case "${code}" in
    200|201|204) echo "UP (${code})" ;;
    000) echo "DOWN (no response)" ;;
    *) echo "NOT READY (${code})" ;;
  esac
}

# Poll URL until HTTP 200 (or attempts exhausted).
# Progress → stderr; final HTTP code only → stdout (for capture).
wait_http_ok() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"
  local sleep_s="${4:-2}"
  local i code="000"
  echo "Waiting for ${label}..." >&2
  for i in $(seq 1 "${attempts}"); do
    code="$(http_code "${url}")"
    if [ "${code}" = "200" ]; then
      echo "  ${label} ready after ~$((i * sleep_s))s" >&2
      echo "${code}"
      return 0
    fi
    sleep "${sleep_s}"
  done
  echo "  ${label} still not ready (last=$(status_label "${code}"))" >&2
  echo "${code}"
  return 1
}

print_base_verify() {
  cat <<EOF

=== Base setup complete (resources started) ===
Mode:     $(mode_label "${MODE}")
Logs:     ${LOG_DIR}
Endpoint: TRITON_ENDPOINT_NMT=${NMT_ENDPOINT} (seeded at migrate; no PATCH)

Apps are starting in the background. Status is re-checked after the UI step.
Inference first pip may still be running (en_core_web_lg ~588 MB) — see:
  tail -f ${LOG_DIR}/inference.log

EOF
}

print_login_sample_curls() {
  cat <<EOF

# Sample checks (no UI) — auth docs + login API
curl -s -o /dev/null -w "auth:%{http_code}\\n" http://127.0.0.1:${AUTH_SERVICE_PORT}/docs
curl -s -o /dev/null -w "core:%{http_code}\\n" http://127.0.0.1:${PLATFORM_CORE_PORT}/docs
curl -s http://127.0.0.1:${INFERENCE_SERVICE_PORT}/health

TOKEN=\$(curl -s -X POST http://127.0.0.1:${AUTH_SERVICE_PORT}/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \\
  | ${PYTHON_BIN} -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
echo "token length: \${#TOKEN}"

EOF
}

# After UI step: wait/poll backends (+ UI if started), print status, then NMT prompt.
print_stack_status() {
  local ui_wanted="${1:-0}"
  local auth_c core_c inf_c ui_c
  # Auth/core pip+uvicorn often needs 1–3 min; UI npm ~1–2 min; inference can be longer (en_core_web_lg).
  local apps_attempts=90   # ~3 min
  local ui_attempts=60     # ~2 min
  local inf_attempts=30    # ~1 min extra poll (do not block NMT forever)
  local wait_sleep=2

  echo
  echo "=== Stack status check (before NMT) ==="
  echo "Ports: auth=${AUTH_SERVICE_PORT} core=${PLATFORM_CORE_PORT} inference=${INFERENCE_SERVICE_PORT} ui=3000"

  auth_c="$(wait_http_ok "http://127.0.0.1:${AUTH_SERVICE_PORT}/docs" "auth (:${AUTH_SERVICE_PORT})" "${apps_attempts}" "${wait_sleep}" || true)"
  core_c="$(wait_http_ok "http://127.0.0.1:${PLATFORM_CORE_PORT}/docs" "platform-core (:${PLATFORM_CORE_PORT})" "${apps_attempts}" "${wait_sleep}" || true)"
  # Short poll for inference; still continue if installing.
  inf_c="$(wait_http_ok "http://127.0.0.1:${INFERENCE_SERVICE_PORT}/health" "inference (:${INFERENCE_SERVICE_PORT})" "${inf_attempts}" "${wait_sleep}" || true)"

  if [ "${ui_wanted}" = 1 ]; then
    ui_c="$(wait_http_ok "http://127.0.0.1:3000/" "simple-ui (:3000)" "${ui_attempts}" "${wait_sleep}" || true)"
  fi

  echo
  echo "Status:"
  printf "  %-22s %s\n" "auth (:${AUTH_SERVICE_PORT})" "$(status_label "${auth_c}")"
  printf "  %-22s %s\n" "platform-core" "$(status_label "${core_c}")"
  printf "  %-22s %s\n" "inference" "$(status_label "${inf_c}")"
  if [ "${ui_wanted}" = 1 ]; then
    printf "  %-22s %s\n" "simple-ui" "$(status_label "${ui_c}")"
  else
    printf "  %-22s %s\n" "simple-ui" "skipped"
  fi

  echo
  if [ "${ui_wanted}" = 1 ]; then
    if [ "${ui_c}" = "200" ]; then
      echo "Visit: http://127.0.0.1:3000"
      echo "Login: admin@ai4inclusion.org / ADMIN_PASSWORD (from docker-compose/.env / seeded admin)"
    else
      echo "Simple UI not ready yet — check: tail -f ${LOG_DIR}/simple-ui.log"
      echo "When ready, visit: http://127.0.0.1:3000"
    fi
  else
    echo "UI was not started. Sample curls for login / health:"
    print_login_sample_curls
  fi

  if [ "${auth_c}" != "200" ] || [ "${core_c}" != "200" ]; then
    echo "NOTE: auth/platform-core not 200 yet — check logs under ${LOG_DIR}/"
  fi
  if [ "${inf_c}" != "200" ]; then
    echo "NOTE: inference may still be installing deps — tail -f ${LOG_DIR}/inference.log"
  fi
  echo
}

print_nmt_verify() {
  cat <<EOF

==============================================================================
  NMT started — run these checks one at a time (copy each block fully)
==============================================================================

--- 1) Triton ready (expect: triton:200) ---
curl -s -o /dev/null -w "triton:%{http_code}\\n" http://127.0.0.1:8000/v2/health/ready

--- 2) Direct Triton translate (first call may download weights; expect Hindi in OUTPUT_TEXT) ---
curl -s -X POST http://127.0.0.1:8000/v2/models/nmt/infer \\
  -H "Content-Type: application/json" \\
  -d '{"inputs":[{"name":"INPUT_TEXT","shape":[1,1],"datatype":"BYTES","data":["Hello, how are you?"]},{"name":"INPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["en"]},{"name":"OUTPUT_LANGUAGE_ID","shape":[1,1],"datatype":"BYTES","data":["hi"]}]}'

--- 3) Login (seeded password is literally ADMIN_PASSWORD unless you set ADMIN_DEFAULT_PASSWORD) ---
TOKEN=\$(curl -s -X POST http://127.0.0.1:${AUTH_SERVICE_PORT}/api/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{"email":"admin@ai4inclusion.org","password":"ADMIN_PASSWORD","remember_me":false}' \\
  | ${PYTHON_BIN} -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
echo "token length: \${#TOKEN}"

--- 4) NMT via inference API (expect Hindi in output[].target) ---
curl -s -X POST http://127.0.0.1:${INFERENCE_SERVICE_PORT}/api/v1/nmt/inference \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$TOKEN" \\
  -d '{"input":[{"source":"Hello, how are you?"}],"config":{"serviceId":"${NMT_SERVICE_ID}","language":{"sourceLanguage":"en","targetLanguage":"hi"}}}'

--- Optional UI ---
EOF
  if [ "${STARTED_UI}" = 1 ]; then
    echo "Open http://127.0.0.1:3000 → NMT card (not LLM)"
    echo "  log: ${LOG_DIR}/simple-ui.log"
  else
    echo "UI was not started in this run."
  fi
  cat <<EOF

--- Cleanup later ---
bash ${COMPOSE}/scripts/cleanup-local.sh
# also delete HF model cache:  REMOVE_HF_CACHE=1 bash ${COMPOSE}/scripts/cleanup-local.sh

==============================================================================
EOF
}

start_svc() {
  local dir="$1" port="$2" module="$3" log="$4"
  rm -rf "${dir}/.venv"
  (
    cd "${dir}"
    "${PYTHON_BIN}" -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    python -m pip install -U pip
    python -m pip install -r requirements.txt
    exec python -m uvicorn "${module}" --host 0.0.0.0 --port "${port}" --reload
  ) >"${log}" 2>&1 &
  echo $! > "${log}.pid"
  echo "started ${dir} pid=$(cat "${log}.pid") log=${log}"
}

########################################
# Prerequisites (print versions when done)
########################################
echo "=== Prerequisite checks ==="
need docker
need curl
resolve_python
[ -t 0 ] || die "This script is interactive — run it from a terminal (TTY)."
[ -f "${COMPOSE}/docker-compose.yml" ] || die "missing ${COMPOSE}/docker-compose.yml"
docker info >/dev/null 2>&1 || die "Docker daemon not reachable (docker info failed)"

DOCKER_VER="$(docker --version 2>/dev/null || echo unknown)"
COMPOSE_VER="$(docker compose version 2>/dev/null || echo unknown)"
PY_VER="$("${PYTHON_BIN}" --version 2>/dev/null || echo unknown)"
CURL_VER="$(curl --version 2>/dev/null | head -n1 || echo unknown)"

echo "  docker:         ${DOCKER_VER}"
echo "  docker compose: ${COMPOSE_VER}"
echo "  docker daemon:  reachable"
echo "  python:         ${PY_VER} (${PYTHON_BIN})"
echo "  curl:           ${CURL_VER}"
echo "  compose file:   ${COMPOSE}/docker-compose.yml"
echo "  TTY:            ok"
echo "=== Prerequisites OK ==="
echo

echo "=== Fresh interactive setup ==="
echo "CORE=${CORE}"
echo "COMPOSE=${COMPOSE}"
echo "AI4I_LOCAL=${AI4I_LOCAL}"
echo

########################################
# 0) Refuse if stack already running
########################################
if stack_running; then
  cat >&2 <<EOF
ERROR: an existing local stack was detected on this machine
  (ai4i-* / indictrans containers, listeners on configured host ports, and/or setup PIDs).

This script will NOT tear it down. For a fresh install:

  bash "${SCRIPT_DIR}/cleanup-local.sh"
  bash "${SCRIPT_DIR}/setup-local.sh"

Or change AUTH_SERVICE_PORT / PLATFORM_CORE_PORT / INFERENCE_SERVICE_PORT in
docker-compose/.env if the conflict is a non-AI4I process, then re-run after
cleanup of any AI4I leftovers.
EOF
  exit 1
fi
echo "=== 0) No existing local stack detected ==="
load_host_ports
echo "Host uvicorn ports: auth=${AUTH_SERVICE_PORT} core=${PLATFORM_CORE_PORT} inference=${INFERENCE_SERVICE_PORT} (UI :3000, NMT :8000/:8002 fixed)"
echo

select_mode

# Fail early if any host port needed for this mode is busy (do not skip services later).
preflight_ports_for_mode

########################################
# 1) App-minimal Compose
########################################
echo
echo "=== 1) App-minimal: Postgres + Redis ==="
confirm "Start postgres + redis and wait until healthy?" y || { echo "Aborted."; exit 0; }
cd "${COMPOSE}"
docker compose up -d postgres redis
wait_healthy ai4i-postgres 60 2
wait_healthy ai4i-redis 60 2
docker compose ps

########################################
# 2) Logging profile
########################################
if [ "${ENABLE_LOGGING}" = 1 ]; then
  echo
  echo "=== 2) Logging profile ==="
  if confirm "Start logging stack (OpenSearch / Dashboards / Fluent Bit)?" y; then
    map_count="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
    if [ "${map_count}" -lt 262144 ] 2>/dev/null; then
      echo "OpenSearch needs vm.max_map_count >= 262144 (current: ${map_count})."
      if confirm "Run: sudo sysctl -w vm.max_map_count=262144 ?" y; then
        sudo sysctl -w vm.max_map_count=262144
      else
        echo "WARNING: continuing without raising vm.max_map_count — OpenSearch may fail."
      fi
    fi
    # Fluent Bit depends on Kafka — start broker first (also covers optional tracing bus).
    # Do NOT use bare --profile logging up -d alone against older packs that started
    # older packs also started etcd/apisix; this pack does not include them.
    if [ "${ENABLE_TRACING}" != 1 ]; then
      echo "Note: Fluent Bit needs Kafka — starting kafka + kafka-init for the log pipeline."
    fi
    docker compose up -d kafka kafka-init
    wait_healthy ai4i-kafka 90 3
    docker compose up -d opensearch opensearch-dashboards fluent-bit
    ENABLE_TRACING=1
    docker compose ps -a
  else
    ENABLE_LOGGING=0
    echo "Skipped logging profile."
  fi
fi

########################################
# 3) Optional tracing (Kafka)
########################################
if [ "${ENABLE_TRACING}" = 1 ]; then
  echo
  echo "=== 3) Optional tracing: Kafka ==="
  if docker inspect -f '{{.State.Health.Status}}' ai4i-kafka 2>/dev/null | grep -qx healthy; then
    echo "Kafka already healthy (started with logging) — skipping."
  elif confirm "Start kafka + kafka-init?" y; then
    docker compose up -d kafka kafka-init
    wait_healthy ai4i-kafka 90 3
    docker compose ps -a
  else
    ENABLE_TRACING=0
    echo "Skipped Kafka."
  fi
fi

########################################
# 4) Monitoring profile
########################################
if [ "${ENABLE_MONITORING}" = 1 ]; then
  echo
  echo "=== 4) Monitoring profile ==="
  if confirm "Start monitoring stack (Prometheus / Grafana / Alertmanager / exporters)?" y; then
    # alertmanager.yml is gitignored (sync may write SMTP secrets). Seed from default.
    am_cfg="${COMPOSE}/config/alertmanager/alertmanager.yml"
    am_default="${COMPOSE}/config/alertmanager/alertmanager.default.yml"
    if [ ! -f "${am_cfg}" ] && [ -f "${am_default}" ]; then
      cp "${am_default}" "${am_cfg}"
      echo "Seeded config/alertmanager/alertmanager.yml from alertmanager.default.yml"
    fi
    # platform-core sync creates these; empty stubs keep Prometheus rule_files happy.
    rules_dir="${COMPOSE}/config/prometheus/rules"
    mkdir -p "${rules_dir}"
    for f in application-alerts.yml infrastructure-alerts.yml; do
      if [ ! -f "${rules_dir}/${f}" ]; then
        printf 'groups: []\n' > "${rules_dir}/${f}"
      fi
    done
    sync_prometheus_host_targets
    docker compose up -d prometheus alertmanager grafana node-exporter kafka-exporter
    docker compose ps
  else
    ENABLE_MONITORING=0
    echo "Skipped monitoring profile."
  fi
fi

########################################
# 5) Env + migrations
########################################
echo
echo "=== 5) Service env + DB migrations ==="
echo "Seeds TRITON_ENDPOINT_NMT=${NMT_ENDPOINT} in repo-root .env before migrate."
confirm "Set up env for all services and run DB migrations?" y || { echo "Aborted before migrate."; exit 0; }

cd "${COMPOSE}"
echo "Generating per-service .env files..."
SETUP_ENV_FROM_LOCAL=1 ./scripts/setup-env.sh
if grep -q '^TRITON_ENDPOINT_NMT=' "${CORE}/.env" 2>/dev/null; then
  sed -i.bak "s|^TRITON_ENDPOINT_NMT=.*|TRITON_ENDPOINT_NMT=${NMT_ENDPOINT}|" "${CORE}/.env"
  rm -f "${CORE}/.env.bak"
else
  echo "TRITON_ENDPOINT_NMT=${NMT_ENDPOINT}" >> "${CORE}/.env"
fi
echo "Seeded $(grep '^TRITON_ENDPOINT_NMT=' "${CORE}/.env")"

# Fail fast if host cannot reach published Postgres (common after VPN/subnet clash).
p_pg="$(env_port POSTGRES_PORT 5432)"
echo "Checking host → Postgres :${p_pg} (3s timeout)..."
if ! timeout 3 bash -c "echo >/dev/tcp/127.0.0.1/${p_pg}" 2>/dev/null; then
  cat >&2 <<EOF
ERROR: Postgres container may be healthy, but this host cannot open TCP 127.0.0.1:${p_pg}
(migrations would hang for minutes). Typical cause: COMPOSE_SUBNET overlaps a VPN route
(e.g. 172.31.0.0/16 via tun0).

Fix:
  1) In ${COMPOSE}/.env set COMPOSE_SUBNET=172.28.0.0/16  (already the pack default)
  2) Recreate the network:
       cd ${COMPOSE}
       docker compose --profile monitoring --profile logging down
       docker compose --profile monitoring --profile logging up -d
  3) Verify:  PGPASSWORD=… psql -h 127.0.0.1 -p ${p_pg} -U postgres -c 'select 1'
  4) Re-run setup (or only migrate) once that returns quickly.
EOF
  exit 1
fi
echo "  Postgres port reachable."

cd "${CORE}"
echo "Installing Alembic/migration deps (fresh .venv via ${PYTHON_BIN})..."
rm -rf .venv
"${PYTHON_BIN}" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r infrastructure/databases/requirements.txt
echo "Running migrations (first DB can take a minute — creating schema/seed)..."
echo "→ ai4iplatform_auth"
./scripts/migrate.sh ai4iplatform_auth upgrade
echo "→ ai4i_platform_db"
./scripts/migrate.sh ai4i_platform_db upgrade
echo "→ ai4iplatform_core (upgrade heads)"
./scripts/migrate.sh ai4iplatform_core upgrade heads
echo "Migrations finished."
deactivate

########################################
# 6) Host apps
########################################
echo
echo "=== 6) Start host apps (auth / platform-core / inference) ==="
echo "Using ports from ${COMPOSE}/.env:"
echo "  AUTH_SERVICE_PORT=${AUTH_SERVICE_PORT}"
echo "  PLATFORM_CORE_PORT=${PLATFORM_CORE_PORT}"
echo "  INFERENCE_SERVICE_PORT=${INFERENCE_SERVICE_PORT}"
confirm "Start uvicorn apps in the background?" y || { echo "Skipped apps. Infra + migrate done."; print_base_verify; exit 0; }

start_svc "${CORE}/services/auth-service" "${AUTH_SERVICE_PORT}" "app.main:app" "${LOG_DIR}/auth.log"
sleep 2
start_svc "${CORE}/services/platform-core-service" "${PLATFORM_CORE_PORT}" "app.main:app" "${LOG_DIR}/platform-core.log"
sleep 2
start_svc "${CORE}/services/inference-service" "${INFERENCE_SERVICE_PORT}" "main:app" "${LOG_DIR}/inference.log"

echo
echo "Apps started (first inference pip install may take several minutes — en_core_web_lg ~588 MB)."
echo "  auth log:       ${LOG_DIR}/auth.log"
echo "  platform-core:  ${LOG_DIR}/platform-core.log"
echo "  inference:      ${LOG_DIR}/inference.log"

print_base_verify

########################################
# 7) Optional Simple UI
########################################
echo "=== 7) Simple UI (optional) ==="
echo "UI proxies to auth/platform-core/inference (no APISIX)."
echo "Simple UI is fixed on :3000 (free the port if busy — not configurable via .env)."
if confirm "Start Simple UI (Next.js on :3000) now?" n; then
  require_ports_free "3000|simple-ui (Next.js)|fixed :3000"

  echo "Checking Node.js prerequisites for Simple UI..."
  if ! command -v node >/dev/null 2>&1; then
    die "node not found. Install Node.js 18+ then re-run setup or start UI manually."
  fi
  if ! command -v npm >/dev/null 2>&1; then
    die "npm not found. Install npm (with Node.js 18+) then re-run setup or start UI manually."
  fi
  node_ver="$(node -v 2>/dev/null | sed 's/^v//')"
  node_major="${node_ver%%.*}"
  echo "  node $(node -v)   npm $(npm -v)"
  if [ -z "${node_major}" ] || [ "${node_major}" -lt 18 ] 2>/dev/null; then
    die "Node.js 18+ required (found v${node_ver}). Upgrade Node, then re-run setup."
  fi
  echo "=== Node prerequisites OK ==="

  UI_DIR="${CORE}/frontend/simple-ui"
  [ -f "${UI_DIR}/package.json" ] || die "missing ${UI_DIR}/package.json"
  [ -f "${UI_DIR}/.env" ] || die "missing ${UI_DIR}/.env — re-run setup-env (step 5)"

  sync_simple_ui_env_ports

  # Ensure NMT card is enabled for local E2E (setup-env copies env.template).
  if grep -q '^ENABLED_TASK_TYPES=' "${UI_DIR}/.env" 2>/dev/null; then
    sed -i.bak 's|^ENABLED_TASK_TYPES=.*|ENABLED_TASK_TYPES=llm,nmt|' "${UI_DIR}/.env"
    rm -f "${UI_DIR}/.env.bak"
  else
    echo 'ENABLED_TASK_TYPES=llm,nmt' >> "${UI_DIR}/.env"
  fi
  grep -E '^(ENABLED_TASK_TYPES|API_URL|AUTH_SERVICE_URL|PLATFORM_CORE_SERVICE_URL|INFERENCE_SERVICE_URL)=' "${UI_DIR}/.env"

  UI_LOG="${LOG_DIR}/simple-ui.log"
  (
    cd "${UI_DIR}"
    npm install
    exec npm run dev
  ) >"${UI_LOG}" 2>&1 &
  echo $! > "${UI_LOG}.pid"
  STARTED_UI=1
  echo "Simple UI starting in background pid=$(cat "${UI_LOG}.pid") log=${UI_LOG}"
  echo "Visit http://127.0.0.1:3000 when ready"
else
  echo "Skipping Simple UI."
fi

print_stack_status "${STARTED_UI}"

########################################
# 8) Optional NMT Triton (HF token only here)
########################################
echo "=== 8) NMT Triton (optional add-on) ==="
echo "Extra RAM/disk: see MINIMAL-INFRA-REQUIREMENTS.md §2.5"
echo "Requires: model-hosting/nmt-triton, HuggingFace Read token, ~40GB+ disk for image/cache."
echo "NMT publish ports: :8000 / :8002 (→ TRITON_ENDPOINT_NMT=${NMT_ENDPOINT})"
if ! confirm "Continue with NMT Triton on this host now?" n; then
  echo
  echo "Skipping NMT. You can build/run it later (SETUP-GUIDE Step 9)."
  echo "Cleanup later: bash ${COMPOSE}/scripts/cleanup-local.sh"
  exit 0
fi

NMT_SRC="$(resolve_nmt)"
if [ -z "${NMT_SRC}" ]; then
  echo "nmt-triton not found under ${AI4I_LOCAL}/model-hosting/nmt-triton"
  read -r -p "Path to nmt-triton (directory with Dockerfile), or Enter to abort NMT: " NMT_SRC || true
  if [ -z "${NMT_SRC}" ] || [ ! -f "${NMT_SRC}/Dockerfile" ]; then
    echo "Skipping NMT (no valid NMT_SRC)."
    echo "Cleanup later: bash ${COMPOSE}/scripts/cleanup-local.sh"
    exit 0
  fi
fi
echo "NMT_SRC=${NMT_SRC}"

if [ -z "${HF_TOKEN:-}" ]; then
  echo
  echo "HuggingFace Read token required (IndicTrans2 gated weights)."
  echo "Create at https://huggingface.co/settings/tokens — accept model access first."
  read -r -s -p "HF_TOKEN (input hidden): " HF_TOKEN
  echo
  [ -n "${HF_TOKEN}" ] || die "HF_TOKEN is empty — cannot start NMT"
else
  echo "Using HF_TOKEN from environment."
fi

if ! confirm "Build (if needed) and run indictrans on ports 8000/8002?" y; then
  echo "Skipping NMT container start."
  exit 0
fi

require_ports_free \
  "8000|NMT Triton HTTP|fixed :8000" \
  "8002|NMT Triton metrics|fixed :8002"

cd "${NMT_SRC}"
if ! docker image inspect nmt-triton-cpu:latest >/dev/null 2>&1 || [ "${FORCE_NMT_BUILD:-}" = 1 ]; then
  if confirm "docker build -t nmt-triton-cpu . (large / several minutes)?" y; then
    docker build -t nmt-triton-cpu .
  else
    echo "No image and build declined — skipping NMT."
    exit 0
  fi
else
  echo "Image nmt-triton-cpu:latest already present (FORCE_NMT_BUILD=1 to rebuild)."
fi

docker rm -f indictrans 2>/dev/null || true
docker run -d \
  -p 8000:8000 -p 8002:8002 \
  -v hf-cache:/cache \
  -e HF_TOKEN="${HF_TOKEN}" \
  --name indictrans \
  nmt-triton-cpu
STARTED_NMT=1
echo "NMT container started (indictrans). First ready/infer may download weights into hf-cache."

print_nmt_verify
