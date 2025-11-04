"""
Create database tables for auth service
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base

async def create_tables():
    """Create all database tables"""
    database_url = os.getenv(
        'DATABASE_URL', 
        'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db'
    )
    
    engine = create_async_engine(database_url, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_tables())
