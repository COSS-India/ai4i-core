"""
ai4icore_bootstrap — Infrastructure building blocks for ALL AI4I-Core microservices.

Provides:
- create_service_app() — single-call app factory
- Database: init_database, close_database, get_db
- Redis: init_redis, close_redis, get_redis
- Rate limiting: setup_rate_limiting, limiter
- Health: create_health_router
- Caching: CacheService
- Schemas: BaseSchema
"""

from .factory import create_service_app, ServiceConfig
from .database import init_database, close_database, get_db, get_engine
from .redis import init_redis, close_redis, get_redis, get_redis_client
from .rate_limit import setup_rate_limiting, limiter
from .health import create_health_router
from .cache import CacheService
from .schemas import BaseSchema
from .versioning import APIVersioning, VersionInfo

__all__ = [
    "create_service_app", "ServiceConfig",
    "init_database", "close_database", "get_db", "get_engine",
    "init_redis", "close_redis", "get_redis", "get_redis_client",
    "setup_rate_limiting", "limiter",
    "create_health_router",
    "CacheService",
    "BaseSchema",
    "APIVersioning", "VersionInfo",
]
