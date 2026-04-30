try:
    from sqlalchemy.orm import declarative_base  # type: ignore
except (ImportError, ModuleNotFoundError):  # pragma: no cover - placeholder if SQLAlchemy not installed yet
    declarative_base = lambda: object  # type: ignore

# Align naming with other services (e.g., smr-service)
AppDBBase = declarative_base()

# Import ORM models so metadata includes them for table creation/migrations.
# If SQLAlchemy isn't installed yet, these imports can be skipped safely by tooling.
try:  # noqa: F401
    from app.models.orm import (  # type: ignore
        PiiType,
        PiiPolicy,
        PolicyPiiType,
        TenantPolicy,
        PiiAuditLog,
    )
except (ImportError, ModuleNotFoundError):
    # Allow repo to install without SQLAlchemy initially.
    pass

