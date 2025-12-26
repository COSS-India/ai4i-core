"""
AI4ICore Database Library

This package provides shared database connection management and session factory
functionality for AI4ICore microservices.

Features:
- Async PostgreSQL connection management
- Session factory creation and management
- Connection health checking
- Graceful connection cleanup
"""

__version__ = "1.0.0"
__author__ = "AI4X Team"
__email__ = "team@ai4x.com"

from .connection_manager import (
    create_database_engine,
    init_database_connections,
    close_database_connections,
    get_database_engine,
    test_database_connection,
)
from .session_factory import (
    create_session_factory,
    init_session_factory,
    get_session_factory,
    get_db_session,
)

__all__ = [
    # Connection management
    "create_database_engine",
    "init_database_connections",
    "close_database_connections",
    "get_database_engine",
    "test_database_connection",
    # Session factory
    "create_session_factory",
    "init_session_factory",
    "get_session_factory",
    "get_db_session",
]

