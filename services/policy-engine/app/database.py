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
