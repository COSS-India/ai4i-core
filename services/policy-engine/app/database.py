import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from ai4icore_env import app_env

from app.db_models import Base

DATABASE_URL = app_env.get_database_url()

logger = logging.getLogger("policy-engine-db")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=5, max_overflow=10)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session():
    async with AsyncSessionLocal() as session:
        yield session


async def init_database():
    """
    Create tables if they do not exist (SMR tenant policies + billing plan tables).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Policy-engine database tables ensured (create_all)")
