#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# Alembic is now located under infrastructure/databases/migrations/postgres
ALEMBIC_INI="$PROJECT_ROOT/infrastructure/databases/migrations/postgres/alembic.ini"
ALEMBIC_DIR="$(cd "$(dirname "$ALEMBIC_INI")" && pwd)"
REGISTRY_SCRIPT="$PROJECT_ROOT/infrastructure/databases/migrations/postgres/alembic/migration_registry.py"

# Load environment variables from .env files if present (local dev).
# In production, env vars are expected to be set by the environment already.
ALEMBIC_ENV="$ALEMBIC_DIR/alembic/.env"
ROOT_ENV="$PROJECT_ROOT/.env"
if [[ -f "$ALEMBIC_ENV" ]]; then
  set -a; source "$ALEMBIC_ENV"; set +a
elif [[ -f "$ROOT_ENV" ]]; then
  set -a; source "$ROOT_ENV"; set +a
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python interpreter not found. Set PYTHON_BIN explicitly." >&2
  exit 1
fi

DATABASE="${1:-all}"
COMMAND="${2:-upgrade}"
EXTRA_ARGS=("${@:3}")

DATABASES=(
  "alerting_db"
  "auth_service_v2_db"
  "config_db"
  "dashboard_db"
  "ai4i_platform_db"
  "metrics_db"
  "model_management_db"
  "multi_tenant_db"
  "telemetry_db"
)

# External databases: services manage their own schemas, we just ensure DB exists
EXTERNAL_DATABASES=(
  "unleash"
)

ensure_policy_service_schema() {
  # policy-service manages its own schema, but we want the repo migration flow
  # to create the tables up-front so the service can start cleanly.
  #
  # DB name is the policy-service default (services/policy-service/env.template).
  local policy_db="policy"

  local pg_user pg_password pg_host pg_port
  pg_user="${POSTGRES_USER:-ai4i_user}"
  pg_password="${POSTGRES_PASSWORD:-}"
  pg_host="${POSTGRES_HOST:-localhost}"
  pg_port="${POSTGRES_PORT:-5432}"

  echo "🔧 Ensuring policy-service database + schema exist..."

  # Ensure DB exists (same approach as external DBs)
  if PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres \
      -tAc "SELECT 1 FROM pg_database WHERE datname='$policy_db'" 2>/dev/null | grep -q 1; then
    print_status "info" "$policy_db already exists"
  else
    if PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres \
        -c "CREATE DATABASE $policy_db;" 2>/dev/null; then
      print_status "applied" "Created database: $policy_db"
    else
      print_status "info" "Failed to create $policy_db (may need manual creation)"
    fi
  fi

  # Create schema objects (idempotent)
  PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d "$policy_db" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS pii_types (
  pii_type_id UUID PRIMARY KEY,
  pii_type_label VARCHAR(255) NOT NULL,
  regex_pattern TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  mask_format VARCHAR(32) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_pii_type_label UNIQUE (pii_type_label)
);

CREATE TABLE IF NOT EXISTS pii_policy (
  policy_id UUID PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  description VARCHAR(512),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_global BOOLEAN NOT NULL DEFAULT FALSE,
  supported_languages JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_pii_policy_name UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS policy_pii_types (
  id UUID PRIMARY KEY,
  policy_id UUID NOT NULL,
  pii_type_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_policy_pii_type UNIQUE (policy_id, pii_type_id),
  CONSTRAINT fk_policy_pii_types_policy FOREIGN KEY (policy_id) REFERENCES pii_policy (policy_id) ON DELETE CASCADE,
  CONSTRAINT fk_policy_pii_types_pii_type FOREIGN KEY (pii_type_id) REFERENCES pii_types (pii_type_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tenant_policy (
  id UUID PRIMARY KEY,
  tenant_id VARCHAR(64) NOT NULL,
  policy_id UUID NOT NULL,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_tenant_policy UNIQUE (tenant_id, policy_id),
  CONSTRAINT fk_tenant_policy_policy FOREIGN KEY (policy_id) REFERENCES pii_policy (policy_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pii_audit_logs (
  pii_audit_id UUID PRIMARY KEY,
  trace_id VARCHAR(128),
  tenant_id VARCHAR(64),
  policy_id UUID,
  target_context VARCHAR(255),
  pii_count INTEGER,
  processing_ms INTEGER,
  trace_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_pii_audit_logs_policy FOREIGN KEY (policy_id) REFERENCES pii_policy (policy_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_pii_types_pii_type_label ON pii_types (pii_type_label);
CREATE INDEX IF NOT EXISTS ix_pii_policy_name ON pii_policy (name);
CREATE INDEX IF NOT EXISTS ix_policy_pii_types_policy_id ON policy_pii_types (policy_id);
CREATE INDEX IF NOT EXISTS ix_policy_pii_types_pii_type_id ON policy_pii_types (pii_type_id);
CREATE INDEX IF NOT EXISTS ix_tenant_policy_tenant_id ON tenant_policy (tenant_id);
CREATE INDEX IF NOT EXISTS ix_tenant_policy_policy_id ON tenant_policy (policy_id);
CREATE INDEX IF NOT EXISTS ix_pii_audit_logs_trace_id ON pii_audit_logs (trace_id);
CREATE INDEX IF NOT EXISTS ix_pii_audit_logs_tenant_id ON pii_audit_logs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_pii_audit_logs_policy_id ON pii_audit_logs (policy_id);
SQL

  print_status "applied" "policy-service schema ensured"
  echo
}

print_db_header() {
  local db="$1"
  echo "🌿 =====> $db"
}

print_status() {
  local label="$1"
  local message="$2"
  local icon="•"
  case "$label" in
    check) icon="🍃" ;;
    generated) icon="🌱" ;;
    applied) icon="✅" ;;
    no-change) icon="🌼" ;;
    skipped) icon="⏭️" ;;
    diff) icon="🪴" ;;
    info) icon="ℹ️" ;;
  esac
  printf "  %s %-10s %s\n" "$icon" "[$label]" "$message"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/migrate.sh [database|all] [command] [alembic args...]

Prerequisite:
  Postgres must be running and reachable (e.g. docker compose -f docker-compose-local.yml up -d postgres).
  For host/WSL runs, set POSTGRES_HOST=localhost and POSTGRES_PORT=5434 in
  infrastructure/databases/migrations/postgres/alembic/.env .

Examples:
  ./scripts/migrate.sh all upgrade
  ./scripts/migrate.sh auth_service_v2_db upgrade head
  ./scripts/migrate.sh config_db current
  ./scripts/migrate.sh model_management_db revision --autogenerate -m "add column"
  ./scripts/migrate.sh alerting_db revision -m "manual migration"

Notes:
  - `revision` must target a single database.
  - For `upgrade`, the default Alembic target is `head`.
  - For `downgrade`, the default Alembic target is `-1`.
EOF
}

contains_arg() {
  local target="$1"
  shift
  local arg
  for arg in "$@"; do
    if [[ "$arg" == "$target" ]]; then
      return 0
    fi
  done
  return 1
}

validate_database() {
  local db="$1"
  local known
  for known in "${DATABASES[@]}"; do
    if [[ "$known" == "$db" ]]; then
      return 0
    fi
  done
  echo "Unsupported database: $db" >&2
  exit 1
}

ensure_database_exists() {
  local db="$1"
  "$PYTHON_BIN" "$REGISTRY_SCRIPT" ensure "$db"
}

supports_autogenerate() {
  local db="$1"
  "$PYTHON_BIN" "$REGISTRY_SCRIPT" supports-autogenerate "$db" >/dev/null 2>&1
}

revision_versions_dir() {
  local db="$1"
  echo "$db"
}

has_existing_revisions() {
  local db="$1"
  local vdir
  vdir="$(revision_versions_dir "$db")"
  find "$PROJECT_ROOT/infrastructure/databases/migrations/postgres/alembic/versions/$vdir" -maxdepth 1 -type f -name "*.py" ! -name "__init__.py" | grep -q .
}

run_autogenerate_revision_if_supported() {
  local db="$1"

  if ! supports_autogenerate "$db"; then
    print_status "skipped" "No models registered. Migration generation skipped."
    return 0
  fi

  local revision_message
  revision_message="auto_$(date +%Y%m%d_%H%M%S)"

  local revision_args
  # Let Alembic/env.py and the temp alembic.ini decide the correct version path
  revision_args=(revision --autogenerate)

  if ! has_existing_revisions "$db"; then
    revision_args+=(--head base --splice)
  fi

  revision_args+=(-m "$revision_message")

  run_alembic_with_db_config "$db" "${revision_args[@]}"
}

run_upgrade_flow_for_db() {
  local db="$1"
  shift

  print_db_header "$db"
  ensure_database_exists "$db"

  print_status "check" "Applying existing migrations..."
  run_alembic_with_db_config "$db" upgrade "$@"

  print_status "check" "Generating migration from models if needed..."
  run_autogenerate_revision_if_supported "$db"

  print_status "check" "Applying latest migration state..."
  run_alembic_with_db_config "$db" upgrade "$@"
  echo
}

run_alembic_with_db_config() {
  local db="$1"
  shift
  local temp_ini
  # IMPORTANT: create the temp ini in the same directory as ALEMBIC_INI
  # so that %(here)s in alembic.ini resolves correctly to ALEMBIC_DIR
  temp_ini="$(mktemp "$ALEMBIC_DIR/tmp_alembic_XXXXXX.ini")"
  "$PYTHON_BIN" - <<PY
from pathlib import Path

source = Path("$ALEMBIC_INI")
target = Path("$temp_ini")
db = "$db"
content = source.read_text()
replacement = f"version_locations = {source.parent}/alembic/versions/{db}"
lines = []
for line in content.splitlines():
    if line.startswith("version_locations = "):
        lines.append(replacement)
    else:
        lines.append(line)
target.write_text("\\n".join(lines) + "\\n")
PY
  local output
  local status
  set +e
  output="$(alembic -c "$temp_ini" -x "db=$db" "$@" 2>&1)"
  status=$?
  set -e
  rm -f "$temp_ini"

  format_alembic_output "$output"

  if [[ $status -ne 0 ]]; then
    return $status
  fi
}

format_alembic_output() {
  local output="$1"
  local line

  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "$line" ]] && continue

    if [[ "$line" == *"Context impl PostgresqlImpl."* ]] || [[ "$line" == *"Will assume transactional DDL."* ]]; then
      continue
    fi

    line="${line#INFO  [alembic.runtime.migration] }"
    line="${line#INFO  [alembic.autogenerate.compare] }"
    line="${line#INFO  [alembic.ddl.postgresql] }"
    line="${line#INFO  [alembic.util.messaging] }"
    line="${line#ERROR [alembic.util.messaging] }"
    line="${line#FAILED: }"

    if [[ "$line" == Generating* ]]; then
      print_status "generated" "$line"
    elif [[ "$line" == Running\ upgrade* ]]; then
      print_status "applied" "$line"
    elif [[ "$line" == Running\ downgrade* ]]; then
      print_status "applied" "$line"
    elif [[ "$line" == No\ schema\ changes\ detected* ]]; then
      print_status "no-change" "$line"
    elif [[ "$line" == No\ SQLAlchemy\ models\ registered* ]]; then
      print_status "skipped" "$line"
    elif [[ "$line" == No\ models\ registered* ]]; then
      print_status "skipped" "$line"
    elif [[ "$line" == Detected\ removed\ column* ]] || [[ "$line" == Detected\ added\ column* ]] || [[ "$line" == Detected\ added\ table* ]] || [[ "$line" == Detected\ removed\ table* ]]; then
      print_status "diff" "$line"
    elif [[ "$line" == Detected\ sequence\ named* ]]; then
      continue
    else
      print_status "info" "$line"
    fi
  done <<< "$output"
}

ensure_external_databases() {
  # Create databases for external services that manage their own schemas
  if [[ ${#EXTERNAL_DATABASES[@]} -eq 0 ]]; then
    return
  fi

  echo "🔧 Ensuring external service databases exist..."

  # Get connection info from the first registered DB's env vars
  local pg_user pg_password pg_host pg_port
  pg_user="${POSTGRES_USER:-ai4i_user}"
  pg_password="${POSTGRES_PASSWORD:-}"
  pg_host="${POSTGRES_HOST:-localhost}"
  pg_port="${POSTGRES_PORT:-5432}"

  for ext_db in "${EXTERNAL_DATABASES[@]}"; do
    if PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres \
        -tAc "SELECT 1 FROM pg_database WHERE datname='$ext_db'" 2>/dev/null | grep -q 1; then
      print_status "info" "$ext_db already exists"
    else
      if PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres \
          -c "CREATE DATABASE $ext_db;" 2>/dev/null; then
        print_status "applied" "Created database: $ext_db"
      else
        print_status "info" "Failed to create $ext_db (may need manual creation)"
      fi
    fi
  done
  echo
}

run_for_all_databases() {
  local command="$1"
  shift

  # Ensure external service databases exist before running migrations
  if [[ "$command" == "upgrade" ]]; then
    ensure_external_databases
    ensure_policy_service_schema
  fi

  local db
  for db in "${DATABASES[@]}"; do
    validate_database "$db"
    if [[ "$command" == "upgrade" ]] && [[ "${1:-}" == "head" ]]; then
      run_upgrade_flow_for_db "$db" "$@"
    else
      print_db_header "$db"
      ensure_database_exists "$db"
      run_alembic_with_db_config "$db" "$command" "$@"
      echo
    fi
  done
}

if [[ "$DATABASE" == "-h" || "$DATABASE" == "--help" ]]; then
  usage
  exit 0
fi

cd "$PROJECT_ROOT"

case "$COMMAND" in
  revision)
    if [[ "$DATABASE" == "all" ]]; then
      echo "Revision creation requires a single target database." >&2
      exit 1
    fi
    validate_database "$DATABASE"
    if contains_arg "--autogenerate" "${EXTRA_ARGS[@]}"; then
      if ! supports_autogenerate "$DATABASE"; then
        print_db_header "$DATABASE"
        print_status "skipped" "No models registered. Autogenerate skipped."
        exit 0
      fi
      ensure_database_exists "$DATABASE"
    fi
    # Let Alembic/env.py and the temp alembic.ini decide the correct version path
    REVISION_ARGS=(revision)
    if ! has_existing_revisions "$DATABASE"; then
      REVISION_ARGS+=(--head base --splice)
    fi
    REVISION_ARGS+=("${EXTRA_ARGS[@]}")
    print_db_header "$DATABASE"
    run_alembic_with_db_config "$DATABASE" "${REVISION_ARGS[@]}"
    ;;
  upgrade)
    if [[ "${#EXTRA_ARGS[@]}" -eq 0 ]]; then
      EXTRA_ARGS=("head")
    fi
    if [[ "$DATABASE" == "all" ]]; then
      run_for_all_databases upgrade "${EXTRA_ARGS[@]}"
    else
      validate_database "$DATABASE"
      if [[ "${EXTRA_ARGS[0]}" == "head" ]]; then
        run_upgrade_flow_for_db "$DATABASE" "${EXTRA_ARGS[@]}"
      else
        print_db_header "$DATABASE"
        ensure_database_exists "$DATABASE"
        run_alembic_with_db_config "$DATABASE" upgrade "${EXTRA_ARGS[@]}"
        echo
      fi
    fi
    ;;
  downgrade)
    if [[ "${#EXTRA_ARGS[@]}" -eq 0 ]]; then
      EXTRA_ARGS=("-1")
    fi
    if [[ "$DATABASE" == "all" ]]; then
      run_for_all_databases downgrade "${EXTRA_ARGS[@]}"
    else
      validate_database "$DATABASE"
      print_db_header "$DATABASE"
      ensure_database_exists "$DATABASE"
      run_alembic_with_db_config "$DATABASE" downgrade "${EXTRA_ARGS[@]}"
      echo
    fi
    ;;
  current|history|heads|branches|show|stamp)
    if [[ "$DATABASE" == "all" ]]; then
      run_for_all_databases "$COMMAND" "${EXTRA_ARGS[@]}"
    else
      validate_database "$DATABASE"
      print_db_header "$DATABASE"
      ensure_database_exists "$DATABASE"
      run_alembic_with_db_config "$DATABASE" "$COMMAND" "${EXTRA_ARGS[@]}"
      echo
    fi
    ;;
  *)
    echo "Unsupported command: $COMMAND" >&2
    usage
    exit 1
    ;;
esac
