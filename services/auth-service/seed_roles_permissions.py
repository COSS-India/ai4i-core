"""
Database seeding script for roles and permissions based on the permission matrix.

This script populates the roles, permissions, and role_permissions tables
with the predefined RBAC structure.
"""
import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import Role, Permission, RolePermission, Base

# Permission matrix: role -> list of permissions (format: "resource.action")
PERMISSION_MATRIX = {
    "ADMIN": [
        "users.create", "users.read", "users.update", "users.delete",
        "configs.create", "configs.read", "configs.update", "configs.delete",
        "metrics.read", "metrics.export",
        "alerts.create", "alerts.read", "alerts.update", "alerts.delete",
        "dashboards.create", "dashboards.read", "dashboards.update", "dashboards.delete",
        "services.create", "services.read", "services.delete",
        "models.create", "models.read",
        "apiKey.create", "apiKey.delete", "apiKey.read",
        "roles.assign", "roles.remove", "roles.read"
    ],
    "MODERATOR": [
        "users.read", "users.update",
        "configs.read", "configs.update",
        "metrics.read",
        "alerts.create", "alerts.read", "alerts.update",
        "dashboards.create", "dashboards.read", "dashboards.update",
        "services.read",
        "models.read",
        "apiKey.read",
        "roles.read"
    ],
    "USER": [
        "users.read",
        "configs.read",
        "metrics.read",
        "alerts.read",
        "dashboards.read",
        "services.read",
        "models.read"
    ],
    "GUEST": [
        "dashboards.read",
        "metrics.read"
    ]
}

ROLE_DESCRIPTIONS = {
    "ADMIN": "Full system access with all permissions",
    "MODERATOR": "Moderate access with read and update capabilities",
    "USER": "Standard user with read-only access to most resources",
    "GUEST": "Limited read-only access to dashboards and metrics"
}


async def seed_roles_permissions():
    """Seed roles and permissions into the database"""
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db'
    )
    
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Collect all unique permissions from the matrix
            all_permissions = set()
            for perms in PERMISSION_MATRIX.values():
                all_permissions.update(perms)
            
            # Create or get all permissions
            permission_map = {}  # "resource.action" -> Permission object
            for perm_str in sorted(all_permissions):
                resource, action = perm_str.split(".", 1)
                perm_name = perm_str
                
                # Check if permission already exists
                result = await session.execute(
                    select(Permission).where(Permission.name == perm_name)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    permission_map[perm_str] = existing
                    print(f"✓ Permission '{perm_name}' already exists")
                else:
                    new_perm = Permission(
                        name=perm_name,
                        resource=resource,
                        action=action
                    )
                    session.add(new_perm)
                    permission_map[perm_str] = new_perm
                    print(f"+ Created permission '{perm_name}' ({resource}.{action})")
            
            await session.commit()
            
            # Create or get all roles
            role_map = {}  # role_name -> Role object
            for role_name, perms in PERMISSION_MATRIX.items():
                # Check if role already exists
                result = await session.execute(
                    select(Role).where(Role.name == role_name)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    role_map[role_name] = existing
                    print(f"✓ Role '{role_name}' already exists")
                else:
                    new_role = Role(
                        name=role_name,
                        description=ROLE_DESCRIPTIONS.get(role_name, "")
                    )
                    session.add(new_role)
                    role_map[role_name] = new_role
                    print(f"+ Created role '{role_name}'")
            
            await session.commit()
            
            # Assign permissions to roles
            for role_name, perm_strings in PERMISSION_MATRIX.items():
                role = role_map[role_name]
                
                for perm_str in perm_strings:
                    permission = permission_map[perm_str]
                    
                    # Check if role_permission already exists
                    result = await session.execute(
                        select(RolePermission).where(
                            RolePermission.role_id == role.id,
                            RolePermission.permission_id == permission.id
                        )
                    )
                    existing = result.scalar_one_or_none()
                    
                    if not existing:
                        role_perm = RolePermission(
                            role_id=role.id,
                            permission_id=permission.id
                        )
                        session.add(role_perm)
                        print(f"  → Assigned '{perm_str}' to '{role_name}'")
            
            await session.commit()
            print("\n✅ Successfully seeded roles and permissions!")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error seeding roles and permissions: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_roles_permissions())

