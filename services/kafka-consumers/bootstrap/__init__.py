"""Reusable code shared by every consumer in this service (ARCHITECTURE.md §3).

Not to be confused with ``ai4i_core.bootstrap``, the shared PyPI library — this
package wraps it.  When both are in scope, import the library one by its full
path (``from ai4i_core.bootstrap import init_database``) and this one relatively
(``from bootstrap.consumers import ManagedConsumer``) so the distinction is
visible at the import line.

The names below are re-exported **lazily**, via PEP 562 ``__getattr__``, rather
than imported at the top of this file.  Eager re-exports would mean
``import bootstrap.launcher`` executes this module and therefore imports
``bootstrap.config`` — the one thing §3.2 says the launcher must never do.  It
also keeps ``--list`` and the argument-validation error paths working in an
environment where sqlalchemy or the broker client cannot even be imported.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import-time only for type checkers, never at runtime
    from bootstrap.config import (
        BrokerErrorReporter,
        DatabaseSettings,
        KafkaSettings,
        RedisSettings,
        build_consumer_config,
        get_db_settings,
        get_kafka_settings,
        get_redis_settings,
    )
    from bootstrap.consumers import ManagedConsumer
    from bootstrap.launcher import available_consumers, main
    from bootstrap.lifecycle import (
        add_database,
        close_all_databases,
        close_database_connection,
        get_engine_for,
        infra,
        session_scope,
        shutdown_event,
    )

# name -> submodule it lives in
_EXPORTS = {
    "BrokerErrorReporter": "bootstrap.config",
    "DatabaseSettings": "bootstrap.config",
    "KafkaSettings": "bootstrap.config",
    "RedisSettings": "bootstrap.config",
    "build_consumer_config": "bootstrap.config",
    "get_db_settings": "bootstrap.config",
    "get_kafka_settings": "bootstrap.config",
    "get_redis_settings": "bootstrap.config",
    "ManagedConsumer": "bootstrap.consumers",
    "available_consumers": "bootstrap.launcher",
    "main": "bootstrap.launcher",
    "add_database": "bootstrap.lifecycle",
    "close_all_databases": "bootstrap.lifecycle",
    "close_database_connection": "bootstrap.lifecycle",
    "get_engine_for": "bootstrap.lifecycle",
    "infra": "bootstrap.lifecycle",
    "session_scope": "bootstrap.lifecycle",
    "shutdown_event": "bootstrap.lifecycle",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    import importlib

    return getattr(importlib.import_module(module_name), name)


def __dir__() -> list[str]:
    return __all__
