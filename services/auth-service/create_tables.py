"""
Create database tables for auth service
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base, Role, Permission, UserRole, RolePermission
from ai4icore_env import app_env

async def create_tables():
    """Create all database tables"""
    database_url = app_env.database_url
    
    engine = create_async_engine(database_url, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    print("Database tables created successfully!")
    print("RBAC tables (roles, permissions, user_roles, role_permissions) created successfully!")

if __name__ == "__main__":
    asyncio.run(create_tables())
