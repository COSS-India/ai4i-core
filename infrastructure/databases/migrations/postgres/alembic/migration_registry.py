"""Database registry and metadata loaders for centralized Alembic migrations."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import MetaData, create_engine, text
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
    "auth_db",
    "config_db",
    "dashboard_db",
    "ai4i_platform_db",
    "metrics_db",
    "model_management_db",
    "multi_tenant_db",
    "telemetry_db",
]


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


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
    module = _load_module(
        "ai4i_alembic_dynamic.auth_models",
        PROJECT_ROOT / "services" / "auth-service" / "models.py",
    )
    combined_metadata = MetaData()
    for table in module.Base.metadata.tables.values():
        table.to_metadata(combined_metadata)

    service_model_files = [
        ("asr", PROJECT_ROOT / "services" / "asr-service" / "models" / "database_models.py"),
        ("nmt", PROJECT_ROOT / "services" / "nmt-service" / "models" / "database_models.py"),
        ("tts", PROJECT_ROOT / "services" / "tts-service" / "models" / "database_models.py"),
        ("ner", PROJECT_ROOT / "services" / "ner-service" / "models" / "database_models.py"),
        ("ocr", PROJECT_ROOT / "services" / "ocr-service" / "models" / "database_models.py"),
        (
            "language_detection",
            PROJECT_ROOT / "services" / "language-detection-service" / "models" / "database_models.py",
        ),
        (
            "language_diarization",
            PROJECT_ROOT / "services" / "language-diarization-service" / "models" / "database_models.py",
        ),
        ("llm", PROJECT_ROOT / "services" / "llm-service" / "models" / "database_models.py"),
        (
            "speaker_diarization",
            PROJECT_ROOT / "services" / "speaker-diarization-service" / "models" / "database_models.py",
        ),
        (
            "transliteration",
            PROJECT_ROOT / "services" / "transliteration-service" / "models" / "database_models.py",
        ),
    ]

    replacements = [
        ('ForeignKey("sessions.id"', 'ForeignKey("user_sessions.id"'),
        ("ForeignKey('sessions.id'", "ForeignKey('user_sessions.id'"),
    ]

    for service_name, file_path in service_model_files:
        service_module = _load_module_with_replacements(
            f"ai4i_alembic_dynamic.{service_name}_database_models",
            file_path,
            replacements=replacements,
        )
        for table in service_module.Base.metadata.tables.values():
            table.to_metadata(combined_metadata)

    return combined_metadata


def _load_config_metadata():
    module = _load_module(
        "ai4i_alembic_dynamic.config_models",
        PROJECT_ROOT / "services" / "config-service" / "models" / "database_models.py",
    )
    return module.Base.metadata


def _load_alerting_metadata():
    module = _load_module(
        "ai4i_alembic_dynamic.alerting_models",
        PROJECT_ROOT / "services" / "alerting-service" / "models.py",
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
    module = _load_module(
        "ai4i_alembic_dynamic.policy_engine.db_models",
        PROJECT_ROOT / "services" / "policy-engine" / "app" / "db_models.py",
    )
    return module.Base.metadata


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
    "auth_db": DatabaseSpec(
        name="auth_db",
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

    raise RuntimeError(f"Unable to ensure database '{target_database}' exists: {last_error}")

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
