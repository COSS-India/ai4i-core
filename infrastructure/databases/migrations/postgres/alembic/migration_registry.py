"""Database registry and metadata loaders for centralized Alembic migrations."""

from __future__ import annotations

import importlib
import os
import re
import sys
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
    "ai4iplatform_auth",
    "ai4i_platform_db",
    "ai4iplatform_core",
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


def _load_auth_service_metadata():
    """Load auth-service ORM metadata (users/passwords/tenants/roles/api keys/oauth/token verification)."""
    auth_root = PROJECT_ROOT / "services" / "auth-service"
    auth_path = str(auth_root)
    if auth_path not in sys.path:
        sys.path.insert(0, auth_path)
    # Purge any previously imported `app.*` modules to avoid cross-service collisions.
    for module_name in list(sys.modules.keys()):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)

    module = importlib.import_module("app.models")
    return module.Base.metadata


def _load_core_service_metadata():
    """Load platform-core-service ORM metadata (mm_models/mm_services in ai4iplatform_core schema)."""
    core_root = PROJECT_ROOT / "services" / "platform-core-service"
    core_path = str(core_root)
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    for module_name in list(sys.modules.keys()):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name, None)

    module = importlib.import_module("app.models")
    return module.Base.metadata


def _load_ai4i_platform_metadata():
    metadata = MetaData()

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
    "ai4iplatform_auth": DatabaseSpec(
        name="ai4iplatform_auth",
        user_key="AUTH_DB_USER",
        password_key="AUTH_DB_PASSWORD",
        host_key="AUTH_DB_HOST",
        port_key="AUTH_DB_PORT",
        database_name_key="AUTH_SERVICE_DB_NAME",
        metadata_loader=_load_auth_service_metadata,
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
    "ai4iplatform_core": DatabaseSpec(
        name="ai4iplatform_core",
        user_key="CORE_SERVICE_DB_USER",
        password_key="CORE_SERVICE_DB_PASSWORD",
        host_key="CORE_SERVICE_DB_HOST",
        port_key="CORE_SERVICE_DB_PORT",
        database_name_key="CORE_SERVICE_DB_NAME",
        metadata_loader=_load_core_service_metadata,
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
    # ai4iplatform_core falls back to shared POSTGRES_* vars when CORE_SERVICE_DB_* are absent.
    if name == "ai4iplatform_core":
        db_name = os.getenv("CORE_SERVICE_DB_NAME") or "ai4iplatform_core"
        return {
            "user": _require_env_any([spec.user_key, "POSTGRES_USER"]),
            "password": _require_env_any([spec.password_key, "POSTGRES_PASSWORD"]),
            "host": _require_env_any([spec.host_key, "POSTGRES_HOST", "ALEMBIC_DB_HOST"]),
            "port": _require_env_any([spec.port_key, "POSTGRES_PORT", "ALEMBIC_DB_PORT"]),
            "database": db_name,
        }

    # ai4iplatform_auth falls back to shared AUTH_DB_* vars when AUTH_SERVICE_DB_NAME is absent,
    # ultimately defaulting to the literal database name "ai4iplatform_auth".
    if name == "ai4iplatform_auth":
        db_name = os.getenv("AUTH_SERVICE_DB_NAME") or os.getenv("AUTH_DB_NAME") or "ai4iplatform_auth"
        return {
            "user": _require_env_any([spec.user_key, "POSTGRES_USER"]),
            "password": _require_env_any([spec.password_key, "POSTGRES_PASSWORD"]),
            "host": _require_env_any([spec.host_key, "POSTGRES_HOST", "ALEMBIC_DB_HOST"]),
            "port": _require_env_any([spec.port_key, "POSTGRES_PORT", "ALEMBIC_DB_PORT"]),
            "database": db_name,
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


def _ensure_database(target_database: str, logical_name: str) -> None:
    """Create *target_database* if it does not already exist.

    Both arguments must come from server-controlled sources (env vars or
    string literals) — never from CLI input.  The dispatch table in
    ensure_database_exists() guarantees this so that the taint chain from
    a CLI argument never reaches the CREATE DATABASE statement.
    """
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', target_database):
        raise ValueError(
            f"Unsafe database name '{target_database}': "
            "only letters, digits, and underscores are permitted."
        )
    parts = get_connection_parts(logical_name)
    ai4i_platform_db = os.getenv("AI4I_PLATFORM_DB_NAME", "")
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
                quoted_db = engine.dialect.identifier_preparer.quote(target_database)
                connection.execute(text(f"CREATE DATABASE {quoted_db}"))
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


def _ensure_ai4iplatform_auth() -> None:
    _ensure_database(
        os.getenv("AUTH_SERVICE_DB_NAME") or os.getenv("AUTH_DB_NAME") or "ai4iplatform_auth",
        "ai4iplatform_auth",
    )


def _ensure_ai4i_platform_db() -> None:
    _ensure_database(_require_env("AI4I_PLATFORM_DB_NAME"), "ai4i_platform_db")


def _ensure_ai4iplatform_core() -> None:
    _ensure_database(
        os.getenv("CORE_SERVICE_DB_NAME") or "ai4iplatform_core",
        "ai4iplatform_core",
    )


# Dispatch table keyed by logical database name.  ensure_database_exists()
# looks up the callable here so the CLI argument is only ever used as a
# dict key for lookup — it is never passed as a value to the SQL path.
_ENSURE_DISPATCH: dict[str, object] = {
    "ai4iplatform_auth": _ensure_ai4iplatform_auth,
    "ai4i_platform_db": _ensure_ai4i_platform_db,
    "ai4iplatform_core": _ensure_ai4iplatform_core,
}


def ensure_database_exists(name: str) -> None:
    fn = _ENSURE_DISPATCH.get(name)
    if fn is None:
        supported = ", ".join(DATABASE_ORDER)
        raise ValueError(f"Unsupported database '{name}'. Supported values: {supported}")
    fn()  # type: ignore[operator]

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
