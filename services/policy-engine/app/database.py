import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Default to the internal Docker DNS for Postgres
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://dhruva_user:dhruva_password@postgres:5432/dhruva_platform"
)

logger = logging.getLogger("policy-engine-db")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session


async def init_database():
    """
    Initialize the database by creating the table if it doesn't exist.
    This function is called on service startup.
    """
    async with AsyncSessionLocal() as session:
        try:
            # Create table if it doesn't exist
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS smr_tenant_policies (
                tenant_id VARCHAR(50) PRIMARY KEY,
                latency_policy VARCHAR(20) NOT NULL DEFAULT 'medium',
                cost_policy VARCHAR(20) NOT NULL DEFAULT 'tier_2',
                accuracy_policy VARCHAR(20) NOT NULL DEFAULT 'standard',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            await session.execute(text(create_table_sql))
            await session.commit()
            logger.info("Database table 'smr_tenant_policies' initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database table: {e}")
            await session.rollback()
            raise
