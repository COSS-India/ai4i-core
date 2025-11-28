"""
Create database tables for NMT service.

This script is analogous to the auth-service `create_tables.py` and is
intended to be run once (or during deployments) to ensure that the
`nmt_requests` and `nmt_results` tables exist in the configured
PostgreSQL database.
"""

import asyncio
import os

from sqlalchemy.ext.asyncio import create_async_engine

from models.database_models import Base, NMTRequestDB, NMTResultDB


async def create_tables() -> None:
    """Create NMT-related database tables."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db",
    )

    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        # Only create the NMT tables to avoid interfering with auth-service
        # tables that may be managed separately (e.g., via migrations).
        def _create_nmt_tables(sync_conn):
            Base.metadata.create_all(
                bind=sync_conn,
                tables=[NMTRequestDB.__table__, NMTResultDB.__table__],
            )

        await conn.run_sync(_create_nmt_tables)

    await engine.dispose()
    print("NMT database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(create_tables())




