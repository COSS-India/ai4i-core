"""Database registry and metadata loaders for centralized Alembic migrations."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import (
    MetaData,
    create_engine,
    text,
    Table,
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

# NOTE: app_env must be imported AFTER load_dotenv() below so the singleton
# picks up all environment variables.  The deferred import is done inside
# ensure_database_exists().

ALEMBIC_DIR = Path(__file__).resolve().parent
# PROJECT_ROOT used to be the repository root when Alembic lived at the top level.
# After moving Alembic under infrastructure/databases/migrations/postgres,
# ALEMBIC_DIR is now .../infrastructure/databases/migrations/postgres/alembic.
# We need PROJECT_ROOT to still point to the repo root so that paths like
# PROJECT_ROOT / "services" / "<service-name>" / "models.py" continue to work.
#
# Repo layout (from ALEMBIC_DIR.parents):
#   parents[0] = .../postgres
#   parents[1] = .../migrations
#   parents[2] = .../databases
#   parents[3] = .../infrastructure
#   parents[4] = .../ai4i-core   <-- actual project root
PROJECT_ROOT = ALEMBIC_DIR.parents[4]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(ALEMBIC_DIR / ".env", override=True)


@dataclass(frozen=True)
class DatabaseSpec:
    name: str
    user_key: str
    password_key: str
    host_key: str
    port_key: str
    database_name_key: str
    metadata_loader: Optional[Callable[[], object]] = None


DATABASE_ORDER = [
    "alerting_db",
    "auth_service_v2_db",
    "config_db",
    "dashboard_db",
    "ai4i_platform_db",
    "metrics_db",
    "model_management_db",
    "policy_db",
    "multi_tenant_db",
    "telemetry_db",
]


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def _require_env_any(keys: list[str]) -> str:
    """
    Return the first non-empty env var value among keys, else raise.
    Useful for optional per-service overrides that can fall back to shared POSTGRES_* vars.
    """
    for key in keys:
        value = os.getenv(key)
        if value:
            return value
    raise ValueError(f"Missing required environment variable (any of): {', '.join(keys)}")


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_module_with_replacements(
    module_name: str,
    file_path: Path,
    replacements: list[tuple[str, str]] | None = None,
):
    source = file_path.read_text()
    for old, new in replacements or []:
        source = source.replace(old, new)

    module = types.ModuleType(module_name)
    module.__file__ = str(file_path)
    sys.modules[module_name] = module
    exec(compile(source, str(file_path), "exec"), module.__dict__)
    return module


def _with_temp_module(name: str, module: types.ModuleType, loader: Callable[[], object]):
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        return loader()
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def _ensure_package(name: str) -> None:
    if name in sys.modules:
        return

    package = types.ModuleType(name)
    package.__path__ = []  # type: ignore[attr-defined]
    sys.modules[name] = package


def _load_auth_metadata():
    # Start from auth-service-v2 core metadata (users/sessions/roles/api keys/oauth)
    module_metadata = _load_auth_service_v2_metadata()
    combined_metadata = MetaData()
    for table in module_metadata.tables.values():
        table.to_metadata(combined_metadata)

    service_model_files = [
        ("asr", PROJECT_ROOT / "services" / "asr-service" / "app" / "models" / "asr.py"),
        ("nmt", PROJECT_ROOT / "services" / "nmt-service" / "app" / "models" / "nmt.py"),
        ("tts", PROJECT_ROOT / "services" / "tts-service" / "app" / "models" / "tts.py"),
        ("ner", PROJECT_ROOT / "services" / "ner-service" / "app" / "models" / "ner.py"),
        ("ocr", PROJECT_ROOT / "services" / "ocr-service" / "app" / "models" / "ocr.py"),
        (
            "language_detection",
            PROJECT_ROOT / "services" / "language-detection-service" / "app" / "models" / "language_detection.py",
        ),
        (
            "language_diarization",
            PROJECT_ROOT / "services" / "language-diarization-service" / "app" / "models" / "language_diarization.py",
        ),
        ("llm", PROJECT_ROOT / "services" / "llm-service" / "app" / "models" / "llm.py"),
        (
            "speaker_diarization",
            PROJECT_ROOT / "services" / "speaker-diarization-service" / "app" / "models" / "speaker_diarization.py",
        ),
        (
            "transliteration",
            PROJECT_ROOT / "services" / "transliteration-service" / "app" / "models" / "transliteration.py",
        ),
        (
            "audio_lang_detection",
            PROJECT_ROOT / "services" / "audio-lang-detection-service" / "app" / "models" / "audio_lang_detection.py",
        ),
    ]

    replacements = [
        ('ForeignKey("sessions.id"', 'ForeignKey("user_sessions.id"'),
        ("ForeignKey('sessions.id'", "ForeignKey('user_sessions.id'"),
    ]

    # Tables already managed by auth-service-v2; skip stubs/duplicates from
    # service model files so autogenerate doesn't create spurious tables
    # (e.g. a "sessions" stub when auth-service-v2 uses "user_sessions").
    auth_table_names = set(combined_metadata.tables.keys()) | {"sessions"}

    for service_name, file_path in service_model_files:
        service_module = _load_module_with_replacements(
            f"ai4i_alembic_dynamic.{service_name}_database_models",
            file_path,
            replacements=replacements,
        )
        for table in service_module.Base.metadata.tables.values():
            if table.name in auth_table_names:
                continue
            table.to_metadata(combined_metadata)

    return combined_metadata


def _load_auth_service_v2_metadata():
    """Load auth-service-v2 ORM metadata (users/sessions/roles/api keys/oauth)."""
    auth_v2_root = PROJECT_ROOT / "services" / "auth-service-v2"
    v2_path = str(auth_v2_root)
    if v2_path not in sys.path:
        sys.path.insert(0, v2_path)
    # Ensure we import auth-service-v2's `app.models` package, not another service's `app`.
    for module_name in list(sys.modules.keys()):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)

    module = importlib.import_module("app.models")
    return module.Base.metadata


def _load_config_metadata():
    module = _load_module(
        "ai4i_alembic_dynamic.config_models",
        PROJECT_ROOT / "services" / "config-service" / "models" / "database_models.py",
    )
    return module.Base.metadata


def _load_alerting_metadata():
    module = _load_module(
        "ai4i_alembic_dynamic.alerting_models",
        PROJECT_ROOT / "services" / "alert-management-service" / "models.py",
    )
    return module.Base.metadata


def _load_telemetry_metadata():
    module = _load_module(
        "ai4i_alembic_dynamic.telemetry_models",
        PROJECT_ROOT / "services" / "telemetry-service" / "models.py",
    )
    return module.Base.metadata


def _load_model_management_metadata():
    fake_db_connection = types.ModuleType("db_connection")
    fake_db_connection.AppDBBase = declarative_base()
    fake_db_connection.AuthDBBase = declarative_base()

    def loader():
        _load_module(
            "ai4i_alembic_dynamic.model_management.db_models",
            PROJECT_ROOT / "services" / "model-management-service" / "models" / "db_models.py",
        )
        return fake_db_connection.AppDBBase.metadata

    return _with_temp_module("db_connection", fake_db_connection, loader)


def _load_policy_service_metadata():
    """
    Load policy-service ORM metadata (pii types/policies/tenant assignments/audit logs).

    NOTE: policy-service is a FastAPI project that uses the generic package name `app`,
    which can collide with other services that also use `app`. We therefore:
      - add the policy-service root to sys.path
      - purge any previously imported `app` modules from sys.modules
      - import policy-service's `app.db.base` and return its declarative base metadata
    """
    policy_root = PROJECT_ROOT / "services" / "policy-service"
    policy_path = str(policy_root)
    if policy_path not in sys.path:
        sys.path.insert(0, policy_path)

    # Ensure we import policy-service's `app.*`, not another service's `app.*`.
    # SAFETY: This is only safe because our migration entrypoints run databases
    # sequentially in a single process (e.g. `scripts/migrate.sh`). If migrations
    # are ever executed in parallel within the same Python process, purging
    # `app.*` here can corrupt other services' imports mid-run.
    for module_name in list(sys.modules.keys()):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)

    module = importlib.import_module("app.db.base")
    return module.AppDBBase.metadata


def _load_multi_tenant_metadata():
    fake_db_connection = types.ModuleType("db_connection")
    fake_db_connection.TenantDBBase = declarative_base()
    fake_db_connection.AuthDBBase = declarative_base()
    fake_db_connection.ServiceSchemaBase = declarative_base()

    def loader():
        _ensure_package("ai4i_alembic_dynamic")
        _ensure_package("ai4i_alembic_dynamic.multi_tenant")
        _ensure_package("ai4i_alembic_dynamic.multi_tenant.models")

        _load_module(
            "ai4i_alembic_dynamic.multi_tenant.models.enum_tenant",
            PROJECT_ROOT / "services" / "multi-tenant-feature" / "models" / "enum_tenant.py",
        )
        _load_module(
            "ai4i_alembic_dynamic.multi_tenant.models.db_models",
            PROJECT_ROOT / "services" / "multi-tenant-feature" / "models" / "db_models.py",
        )
        return fake_db_connection.TenantDBBase.metadata

    return _with_temp_module("db_connection", fake_db_connection, loader)


def _load_ai4i_platform_metadata():
    # policy-engine service was removed; define all ai4i_platform_db tables
    # inline so autogenerate sees them and doesn't emit spurious DROPs.
    metadata = MetaData()

    Table(
        "smr_tenant_policies",
        metadata,
        Column("tenant_id", String(length=50), primary_key=True, nullable=False),
        Column("latency_policy", String(length=20), nullable=False, server_default="medium"),
        Column("cost_policy", String(length=20), nullable=False, server_default="tier_2"),
        Column("accuracy_policy", String(length=20), nullable=False, server_default="standard"),
        Column("created_at", DateTime(), server_default=text("now()"), nullable=False),
        Column("updated_at", DateTime(), server_default=text("now()"), nullable=False),
    )

    if "pattern_library" not in metadata.tables:
        Table(
            "pattern_library",
            metadata,
            Column("id", Integer(), primary_key=True, nullable=False),
            Column("entity_label", String(length=50), nullable=False),
            Column("lang_code", String(length=10), nullable=False),
            Column("regex_pattern", Text(), nullable=False),
            Column("risk_score", Float(), server_default=text("1.0"), nullable=True),
            Column("is_active", Boolean(), server_default=text("true"), nullable=True),
            UniqueConstraint("entity_label", "lang_code", name="uq_pattern_entity_lang"),
        )

    if "geo_library" not in metadata.tables:
        Table(
            "geo_library",
            metadata,
            Column("id", Integer(), primary_key=True, nullable=False),
            Column("term_text", String(length=100), nullable=False),
            Column("lang_code", String(length=10), nullable=False),
            Column("term_type", String(length=20), nullable=False),
            Column("is_active", Boolean(), server_default=text("true"), nullable=True),
        )

    if "keyword_library" not in metadata.tables:
        Table(
            "keyword_library",
            metadata,
            Column("id", Integer(), primary_key=True, nullable=False),
            Column("word_text", String(length=100), nullable=False),
            Column("category", String(length=20), nullable=False),
            Column("lang_code", String(length=10), nullable=False),
        )

    if "domain_policies" not in metadata.tables:
        Table(
            "domain_policies",
            metadata,
            Column("domain_id", String(length=50), primary_key=True, nullable=False),
            Column("is_active", Boolean(), server_default=text("false"), nullable=True),
            Column("policy_json", JSONB, nullable=False),
            Column("created_at", DateTime(), server_default=text("CURRENT_TIMESTAMP"), nullable=True),
        )

    if "audit_logs" not in metadata.tables:
        Table(
            "audit_logs",
            metadata,
            Column("id", Integer(), primary_key=True, nullable=False),
            Column("trace_id", UUID(as_uuid=True), nullable=True),
            Column("tenant_id", String(length=50), nullable=True),
            Column("domain_id", String(length=50), nullable=True),
            Column("target_context", String(length=20), nullable=True),
            Column("pii_count", Integer(), nullable=True),
            Column("processing_ms", Integer(), nullable=True),
            Column("trace_json", JSONB, nullable=True),
            Column("created_at", DateTime(), server_default=text("CURRENT_TIMESTAMP"), nullable=True),
        )

    if "tenant_pii_domain_map" not in metadata.tables:
        Table(
            "tenant_pii_domain_map",
            metadata,
            Column("tenant_id", String(length=255), primary_key=True, nullable=False),
            Column("domain_id", String(length=50), nullable=False),
            Column("created_at", DateTime(), server_default=text("CURRENT_TIMESTAMP"), nullable=True),
            Column("updated_at", DateTime(), server_default=text("CURRENT_TIMESTAMP"), nullable=True),
        )

    return metadata


DATABASE_SPECS = {
    "alerting_db": DatabaseSpec(
        name="alerting_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="ALERTING_DB_NAME",
        metadata_loader=_load_alerting_metadata,
    ),
    "auth_service_v2_db": DatabaseSpec(
        name="auth_service_v2_db",
        user_key="AUTH_DB_USER",
        password_key="AUTH_DB_PASSWORD",
        host_key="AUTH_DB_HOST",
        port_key="AUTH_DB_PORT",
        database_name_key="AUTH_DB_NAME",
        metadata_loader=_load_auth_metadata,
    ),
    "config_db": DatabaseSpec(
        name="config_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="CONFIG_DB_NAME",
        metadata_loader=_load_config_metadata,
    ),
    "dashboard_db": DatabaseSpec(
        name="dashboard_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="DASHBOARD_DB_NAME",
        metadata_loader=None,
    ),
    "ai4i_platform_db": DatabaseSpec(
        name="ai4i_platform_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="AI4I_PLATFORM_DB_NAME",
        metadata_loader=_load_ai4i_platform_metadata,
    ),
    "metrics_db": DatabaseSpec(
        name="metrics_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="METRICS_DB_NAME",
        metadata_loader=None,
    ),
    "model_management_db": DatabaseSpec(
        name="model_management_db",
        user_key="APP_DB_USER",
        password_key="APP_DB_PASSWORD",
        host_key="APP_DB_HOST",
        port_key="APP_DB_PORT",
        database_name_key="APP_DB_NAME",
        metadata_loader=_load_model_management_metadata,
    ),
    "policy_db": DatabaseSpec(
        name="policy_db",
        user_key="POLICY_DB_USER",
        password_key="POLICY_DB_PASSWORD",
        host_key="POLICY_DB_HOST",
        port_key="POLICY_DB_PORT",
        database_name_key="POLICY_DB_NAME",
        metadata_loader=_load_policy_service_metadata,
    ),
    "multi_tenant_db": DatabaseSpec(
        name="multi_tenant_db",
        user_key="APP_DB_USER",
        password_key="APP_DB_PASSWORD",
        host_key="APP_DB_HOST",
        port_key="APP_DB_PORT",
        database_name_key="MULTI_TENANT_DB_NAME",
        metadata_loader=_load_multi_tenant_metadata,
    ),
    "telemetry_db": DatabaseSpec(
        name="telemetry_db",
        user_key="POSTGRES_USER",
        password_key="POSTGRES_PASSWORD",
        host_key="POSTGRES_HOST",
        port_key="POSTGRES_PORT",
        database_name_key="TELEMETRY_DB_NAME",
        metadata_loader=_load_telemetry_metadata,
    ),
}


def get_database_names() -> list[str]:
    return list(DATABASE_ORDER)


def get_database_spec(name: str) -> DatabaseSpec:
    try:
        return DATABASE_SPECS[name]
    except KeyError as exc:
        supported = ", ".join(DATABASE_ORDER)
        raise ValueError(f"Unsupported database '{name}'. Supported values: {supported}") from exc


def get_database_name(name: str) -> str:
    spec = get_database_spec(name)
    return _require_env(spec.database_name_key)


def get_connection_parts(name: str) -> dict[str, str]:
    spec = get_database_spec(name)
    # policy_db should work in deployed environments without requiring dedicated POLICY_DB_*
    # variables; if those are absent, fall back to the shared POSTGRES_* (or ALEMBIC_DB_*) vars.
    if name == "policy_db":
        return {
            "user": _require_env_any([spec.user_key, "POSTGRES_USER"]),
            "password": _require_env_any([spec.password_key, "POSTGRES_PASSWORD"]),
            "host": _require_env_any([spec.host_key, "POSTGRES_HOST", "ALEMBIC_DB_HOST"]),
            "port": _require_env_any([spec.port_key, "POSTGRES_PORT", "ALEMBIC_DB_PORT"]),
            "database": _require_env_any([spec.database_name_key]),
        }

    return {
        "user": _require_env(spec.user_key),
        "password": _require_env(spec.password_key),
        "host": _require_env(spec.host_key),
        "port": _require_env(spec.port_key),
        "database": _require_env(spec.database_name_key),
    }


def get_sync_url(name: str) -> str:
    parts = get_connection_parts(name)
    return (
        f"postgresql+psycopg2://{quote_plus(parts['user'])}:{quote_plus(parts['password'])}"
        f"@{parts['host']}:{parts['port']}/{parts['database']}"
    )


def get_version_path(name: str) -> Path:
    # Use the dedicated auth-service-v2 migration folder.
    if name == "auth_service_v2_db":
        return ALEMBIC_DIR / "versions" / "auth_service_v2_db"
    return ALEMBIC_DIR / "versions" / name


def get_target_metadata(name: str, strict: bool = False):
    spec = get_database_spec(name)
    if spec.metadata_loader is None:
        return None

    try:
        return spec.metadata_loader()
    except Exception as exc:
        if strict:
            raise RuntimeError(f"Could not load SQLAlchemy metadata for '{name}': {exc}") from exc
        return None


def supports_autogenerate(name: str) -> bool:
    return get_database_spec(name).metadata_loader is not None


def ensure_database_exists(name: str) -> None:
    parts = get_connection_parts(name)
    target_database = parts["database"]
    try:
        from ai4icore_env import app_env
    except ModuleNotFoundError:
        candidate_paths = [
            PROJECT_ROOT / "libs" / "ai4icore_env",
            PROJECT_ROOT / "libs",
        ]
        for candidate in candidate_paths:
            candidate_str = str(candidate)
            if candidate.exists() and candidate_str not in sys.path:
                sys.path.insert(0, candidate_str)
        from ai4icore_env import app_env
    ai4i_platform_db = app_env.ai4i_platform_db_name
    maintenance_databases = tuple(db for db in ("postgres", ai4i_platform_db, target_database) if db)
    last_error: Exception | None = None

    for maintenance_db in maintenance_databases:
        url = (
            f"postgresql+psycopg2://{quote_plus(parts['user'])}:{quote_plus(parts['password'])}"
            f"@{parts['host']}:{parts['port']}/{maintenance_db}"
        )
        try:
            engine = create_engine(url, isolation_level="AUTOCOMMIT", future=True)
            with engine.connect() as connection:
                exists = connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                    {"database_name": target_database},
                ).scalar()
                if exists:
                    return
                if maintenance_db == target_database:
                    return
                connection.execute(text(f'CREATE DATABASE "{target_database}"'))
                return
        except Exception as exc:
            last_error = exc
        finally:
            try:
                engine.dispose()
            except Exception:
                pass

    hint = ""
    if last_error and "Connection refused" in str(last_error):
        hint = (
            "\n\nPostgres is not reachable. Ensure it is running (e.g. from repo root:\n"
            "  docker compose -f docker-compose-local.yml up -d postgres\n"
            "Then ensure infrastructure/databases/migrations/postgres/alembic/.env has\n"
            "POSTGRES_HOST and POSTGRES_PORT for your setup (e.g. localhost and 5434 for host access)."
        )
    raise RuntimeError(f"Unable to ensure database '{target_database}' exists: {last_error}{hint}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Alembic database registry helper")
    parser.add_argument("command", choices=["ensure", "supports-autogenerate"])
    parser.add_argument("databases", nargs="+", help="One or more database names")
    args = parser.parse_args()

    if args.command == "ensure":
        for database in args.databases:
            ensure_database_exists(database)
    elif args.command == "supports-autogenerate":
        exit_code = 0
        for database in args.databases:
            if not supports_autogenerate(database):
                exit_code = 1
        raise SystemExit(exit_code)