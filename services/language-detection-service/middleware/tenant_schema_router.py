"""
Tenant Schema Routing Middleware
Routes database connections to tenant-specific schemas
"""
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text, event
from typing import Dict, Optional
import logging
import os

logger = logging.getLogger(__name__)


class TenantSchemaRouter:
    """
    Manages database connections with tenant schema routing.
    """
    def __init__(self, database_url: str):
        self.database_url = database_url
        self._engines: Dict[str, AsyncEngine] = {}
        self._session_factories: Dict[str, async_sessionmaker] = {}

    def get_tenant_session_factory(self, schema_name: str) -> async_sessionmaker:
        """
        Get or create session factory for tenant schema.
        """
        if schema_name not in self._session_factories:
            # Validate schema name to prevent injection
            if not schema_name or not schema_name.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"Invalid schema name: {schema_name}")

            # Create engine with schema-specific connection
            engine = create_async_engine(
                self.database_url,
                pool_size=10,
                max_overflow=5,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={
                    "timeout": 30,
                    "command_timeout": 30,
                }
            )

            # Add event listener to set search_path on each connection.
            # NOTE: asyncpg's cursor adapter does NOT support context manager protocol,
            # so we must manually close the cursor instead of using "with".
            @event.listens_for(engine.sync_engine, "connect")
            def set_search_path(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                try:
                    cursor.execute(f'SET search_path TO "{schema_name}", public')
                finally:
                    cursor.close()

            self._engines[schema_name] = engine
            self._session_factories[schema_name] = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            logger.info(f"Created session factory for schema: {schema_name}")

        return self._session_factories[schema_name]

    async def get_tenant_session(self, schema_name: str) -> AsyncSession:
        """
        Get database session for tenant schema.
        """
        factory = self.get_tenant_session_factory(schema_name)
        session = factory()

        # Ensure search_path is set
        await session.execute(text(f'SET search_path TO "{schema_name}", public'))
        return session

    async def close_all(self):
        """Close all engines"""
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
        self._session_factories.clear()
