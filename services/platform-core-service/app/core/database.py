"""
Database — re-exports from shared ai4icore_bootstrap.
Core-service uses the same DB infra as every other service.
"""

from ai4icore_core.bootstrap.database import (  # noqa: F401
    init_database,
    close_database,
    get_db,
    get_engine,
)
