"""Centralized Alembic environment for all PostgreSQL databases."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from alembic.operations import ops
from sqlalchemy import MetaData, String, create_engine, pool
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


def _remove_tenants_status_drift(upgrade_ops_obj) -> None:
    """Strip the persistent cosmetic ENUM-vs-Enum drift on tenants.status.

    Alembic 1.12+ reflects postgresql.ENUM differently from sa.Enum even when
    the live schema is correct, causing spurious ALTER COLUMN on every autogenerate
    run.  Remove only those AlterColumnOp entries targeting tenants.status so the
    rest of the migration (if any) is preserved.
    """
    new_ops = []
    for op_obj in upgrade_ops_obj.ops:
        if isinstance(op_obj, ops.AlterColumnOp) and op_obj.table_name == "tenants" and op_obj.column_name == "status":
            continue
        if isinstance(op_obj, ops.ModifyTableOps) and op_obj.table_name == "tenants":
            kept = [
                sub for sub in op_obj.ops
                if not (isinstance(sub, ops.AlterColumnOp) and sub.column_name == "status")
            ]
            if kept:
                op_obj.ops[:] = kept
                new_ops.append(op_obj)
            continue
        new_ops.append(op_obj)
    upgrade_ops_obj.ops[:] = new_ops


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

    # Strip the persistent cosmetic tenants.status ENUM drift before checking again.
    _remove_tenants_status_drift(script.upgrade_ops)
    if script.upgrade_ops.is_empty():
        directives[:] = []
        print(f"No schema changes detected for {target_db} (tenants.status drift suppressed).")
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

    schemas_needed = set()
    for operation in script.upgrade_ops.ops:
        if isinstance(operation, ops.CreateTableOp) and operation.schema:
            schemas_needed.add(operation.schema)
    for schema in sorted(schemas_needed, reverse=True):
        script.upgrade_ops.ops.insert(
            0,
            ops.ExecuteSQLOp(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'),
        )


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Skip reflected objects that are not part of the target metadata.

    This prevents autogenerate from emitting DROP TABLE for tables that
    exist in the database but belong to a different service/migration scope.
    Handles schema-qualified table keys (e.g. "ai4iplatform_core.mm_models").
    """
    if is_autogenerate and reflected and compare_to is None:
        # No model metadata at all – skip everything reflected.
        if not has_model_metadata:
            return False
        # Has model metadata – only include tables/indexes/constraints
        # that are actually declared in the target metadata.
        if type_ == "table":
            schema = getattr(object_, "schema", None)
            qualified_name = f"{schema}.{name}" if schema else name
            return qualified_name in target_metadata.tables or name in target_metadata.tables
        # For non-table objects (indexes, constraints, etc.) on tables
        # outside our metadata, skip them as well.
        table_obj = getattr(object_, "table", None)
        if table_obj is not None:
            tname = getattr(table_obj, "name", table_obj)
            tschema = getattr(table_obj, "schema", None)
            qualified = f"{tschema}.{tname}" if tschema else tname
            return qualified in target_metadata.tables or tname in target_metadata.tables
    return True


def render_item(type_, obj, autogen_context):
    """Render custom type decorators as their underlying SQLAlchemy impl.

    Models loaded via ``migration_registry`` live under a synthetic module
    ``ai4i_alembic_dynamic.*``. If Alembic falls back to default rendering, it
    emits that path in migrations, which raises ``NameError`` at upgrade time.
    Known decorators are mapped to plain ``sa.*`` types here.
    """
    if type_ == "type" and isinstance(obj, TypeDecorator):
        td_cls = type(obj)
        td_mod = getattr(td_cls, "__module__", "") or ""
        impl = getattr(obj, "impl", None)
        if impl is None:
            impl = getattr(td_cls, "impl", None)

        migration_context = getattr(autogen_context, "migration_context", None)
        context_impl = getattr(migration_context, "impl", None)
        if context_impl is not None and hasattr(context_impl, "render_type") and impl is not None:
            try:
                rendered = context_impl.render_type(impl, autogen_context)
                # impl.render_type returns False when the dialect declines — do not
                # treat that like a string (False is not None and False != "").
                if rendered not in (False, None, ""):
                    return rendered
            except Exception:
                pass

        # Synthetic loader module — never emit as Python reference in revisions.
        if "ai4i_alembic_dynamic" in td_mod:
            if isinstance(impl, String):
                ln = getattr(impl, "length", None)
                if ln is not None:
                    return f"sa.String(length={ln})"
                return "sa.String()"
            if td_cls.__name__ == "ServiceUnitTypeEnum":
                return "sa.String(length=50)"

        return False
    return False


def _skip_tenants_status_enum_compare(inspected_column) -> bool:
    """Skip tenants.status comparison during enum migration."""
    if inspected_column is None:
        return False
    return (
        getattr(inspected_column, "name", None) == "status"
        and getattr(getattr(inspected_column, "table", None), "name", None) == "tenants"
    )


def _tenants_status_autogenerate_compare_result(inspected_column):
    """Return True to suppress diff, None to defer to Alembic defaults."""
    if is_autogenerate and _skip_tenants_status_enum_compare(inspected_column):
        return True
    return None


# Temporary autogenerate overrides for ai4iplatform_auth.tenants.status (remove after
# revision c4e8f1a2b3d0 is applied on every environment).
#
# Why: During the tenant_status_enum migration, reflected DB metadata (legacy enum
# labels and/or PostgreSQL default syntax) often disagrees with SQLAlchemy models
# even when the live schema is correct. Returning True tells Alembic "treat as equal"
# so autogenerate does not emit duplicate ALTERs; the hand-written revision
# c4e8f1a2b3d0 owns the enum transition.
#
# Removal: Delete compare_type / compare_server_default below (and their entries in
# get_context_config_kwargs) once all DBs are on the new enum and `alembic revision
# --autogenerate -x db=ai4iplatform_auth` no longer proposes tenants.status changes.
# Do not keep these permanently—they would hide real drift on tenants.status later.


def compare_server_default(
    context,
    inspected_column,
    metadata_column,
    rendered_inspected_default,
    metadata_server_default,
    rendered_metadata_default,
):
    """Alembic autogenerate hook: suppress false diffs on tenants.status server default.

    Purpose:
        During the tenant_status_enum migration, PostgreSQL often reflects the column
        default differently from the SQLAlchemy model (e.g. ``'PENDING'`` vs
        ``'PENDING'::tenant_status_enum``). Autogenerate would otherwise emit a
        redundant ``ALTER COLUMN ... SET DEFAULT`` even though the effective default
        is already correct. The real default change is applied in revision
        c4e8f1a2b3d0.

    Function:
        Called by Alembic for each column when comparing reflected DB schema to
        ``target_metadata`` during ``alembic revision --autogenerate``. Only active
        when ``is_autogenerate`` is true and the column is ``tenants.status``.

        Returns:
            ``True``  — treat inspected and metadata defaults as equal (skip diff).
            ``None``  — defer to Alembic's built-in default comparison.

    Temporary: remove once c4e8f1a2b3d0 is applied everywhere (see block comment above).
    """
    return _tenants_status_autogenerate_compare_result(inspected_column)


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """Alembic autogenerate hook: suppress false diffs on tenants.status column type.

    Purpose:
        While the database still uses legacy enum labels (``activated``,
        ``deactivated``, ``suspended``) or during the transition to
        ``PENDING``/``ACTIVE``/``SUSPENDED``/``DEACTIVATED``, reflected types will
        not match the auth-service model. Autogenerate would emit duplicate
        ``ALTER COLUMN ... TYPE`` operations. Enum relabeling is owned by the
        hand-written revision c4e8f1a2b3d0, not autogenerate.

    Function:
        Called by Alembic for each column when comparing reflected column types to
        model types during ``alembic revision --autogenerate``. Only active when
        ``is_autogenerate`` is true and the column is ``tenants.status``.

        Returns:
            ``True``  — treat inspected and metadata types as equal (skip diff).
            ``None``  — defer to Alembic's built-in type comparison.

    Temporary: remove once c4e8f1a2b3d0 is applied everywhere (see block comment above).
    """
    return _tenants_status_autogenerate_compare_result(inspected_column)


def get_context_config_kwargs() -> dict:
    kwargs = {
        "target_metadata": target_metadata,
        "compare_type": compare_type,
        "compare_server_default": compare_server_default,
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
