"""Centralized Alembic environment for all PostgreSQL databases."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from alembic.operations import ops
from sqlalchemy import MetaData, create_engine, pool
from sqlalchemy.types import TypeDecorator

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from migration_registry import (  # noqa: E402
    get_database_names,
    get_sync_url,
    get_target_metadata,
    get_version_path,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

x_args = context.get_x_argument(as_dictionary=True)
target_db = x_args.get("db")

if not target_db:
    raise SystemExit("Alembic requires a target database. Use: alembic -x db=<database_name> ...")

if target_db not in get_database_names():
    supported = ", ".join(get_database_names())
    raise SystemExit(f"Unsupported database '{target_db}'. Supported values: {supported}")

is_autogenerate = bool(getattr(config.cmd_opts, "autogenerate", False))
target_metadata = get_target_metadata(target_db, strict=is_autogenerate)
version_path = str(get_version_path(target_db))
has_model_metadata = target_metadata is not None
if target_metadata is None:
    target_metadata = MetaData()

config.set_main_option("sqlalchemy.url", get_sync_url(target_db))
config.set_main_option("version_locations", version_path)


def process_revision_directives(migration_context, revision, directives) -> None:
    """Avoid creating empty autogenerate revisions."""
    if not is_autogenerate or not directives:
        return

    if not has_model_metadata:
        directives[:] = []
        print(f"No SQLAlchemy models registered for {target_db}; skipping autogenerate.")
        return

    script = directives[0]
    if script.upgrade_ops.is_empty():
        directives[:] = []
        print(f"No schema changes detected for {target_db}.")
        return

    needs_pgcrypto = False
    for operation in script.upgrade_ops.ops:
        if not isinstance(operation, ops.CreateTableOp):
            continue
        for column in operation.columns:
            server_default = getattr(column, "server_default", None)
            default_sql = str(getattr(server_default, "arg", ""))
            if "gen_random_uuid()" in default_sql:
                needs_pgcrypto = True
                break
        if needs_pgcrypto:
            break

    if needs_pgcrypto:
        script.upgrade_ops.ops.insert(
            0,
            ops.ExecuteSQLOp('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'),
        )


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Skip reflected objects that are not part of the target metadata.

    This prevents autogenerate from emitting DROP TABLE for tables that
    exist in the database but belong to a different service/migration scope.
    """
    if is_autogenerate and reflected and compare_to is None:
        # No model metadata at all – skip everything reflected.
        if not has_model_metadata:
            return False
        # Has model metadata – only include tables/indexes/constraints
        # that are actually declared in the target metadata.
        if type_ == "table":
            return name in target_metadata.tables
        # For non-table objects (indexes, constraints, etc.) on tables
        # outside our metadata, skip them as well.
        table_name = getattr(object_, "table", None)
        if table_name is not None:
            table_name = getattr(table_name, "name", table_name)
            return table_name in target_metadata.tables
    return True


def render_item(type_, obj, autogen_context):
    """Render custom type decorators as their underlying SQLAlchemy impl."""
    if type_ == "type" and isinstance(obj, TypeDecorator):
        impl = getattr(obj, "impl", None)
        if impl is None:
            return False
        # Alembic compatibility: some versions expose renderer on
        # autogen_context.migration_context.impl, not autogen_context.impl.
        migration_context = getattr(autogen_context, "migration_context", None)
        context_impl = getattr(migration_context, "impl", None)
        if context_impl is not None and hasattr(context_impl, "render_type"):
            try:
                return context_impl.render_type(impl, autogen_context)
            except Exception:
                return False
        return False
    return False


def get_context_config_kwargs() -> dict:
    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "include_object": include_object,
        "render_item": render_item,
        "process_revision_directives": process_revision_directives,
    }
    return kwargs


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **get_context_config_kwargs(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, **get_context_config_kwargs())

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
