#!/usr/bin/env python3
"""
Script to update service ID from 'asr_am_ensemble' to 'ai4bharat/indictasr'
in the Model Management database.

This script:
1. Fetches the current service details
2. Updates the service_id in the database
3. Clears Redis cache for both old and new service IDs
"""

import asyncio
import os
import sys
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add the model-management-service to path to import models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'model-management-service'))

from models.db_models import Service, AppDBBase
from models.cache_models_services import ServiceCache


async def update_service_id(
    db_url: str,
    old_service_id: str = 'asr_am_ensemble',
    new_service_id: str = 'ai4bharat/indictasr'
):
    """Update service ID in database and cache"""
    
    # Create async engine
    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as session:
            # 1. Check if old service exists
            result = await session.execute(
                select(Service).where(Service.service_id == old_service_id)
            )
            service = result.scalar_one_or_none()
            
            if not service:
                print(f"❌ Service '{old_service_id}' not found in database")
                return False
            
            print(f"✅ Found service '{old_service_id}':")
            print(f"   Name: {service.name}")
            print(f"   Model ID: {service.model_id}")
            print(f"   Model Version: {service.model_version}")
            print(f"   Endpoint: {service.endpoint}")
            
            # 2. Check if new service_id already exists
            result = await session.execute(
                select(Service).where(Service.service_id == new_service_id)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                print(f"❌ Service '{new_service_id}' already exists!")
                return False
            
            # 3. Update service_id
            await session.execute(
                update(Service)
                .where(Service.service_id == old_service_id)
                .values(service_id=new_service_id)
            )
            await session.commit()
            
            print(f"✅ Successfully updated service_id from '{old_service_id}' to '{new_service_id}'")
            
            # 4. Clear Redis cache
            try:
                # Delete old cache entry
                try:
                    ServiceCache.delete(old_service_id)
                    print(f"✅ Cleared Redis cache for old service_id: {old_service_id}")
                except Exception:
                    print(f"⚠️  No cache found for old service_id: {old_service_id}")
                
                # Delete new cache entry (in case it exists)
                try:
                    ServiceCache.delete(new_service_id)
                    print(f"✅ Cleared Redis cache for new service_id: {new_service_id}")
                except Exception:
                    pass  # Expected if cache doesn't exist
                    
            except Exception as e:
                print(f"⚠️  Warning: Could not clear Redis cache: {e}")
                print("   You may need to clear cache manually or restart the service")
            
            return True
            
    except Exception as e:
        print(f"❌ Error updating service: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


async def main():
    """Main entry point"""
    # Get database URL from environment or use default
    db_url = os.getenv(
        'DATABASE_URL',
        'postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@localhost:5432/model_management_db'
    )
    
    print("=" * 60)
    print("Service ID Update Script")
    print("=" * 60)
    print(f"Old Service ID: asr_am_ensemble")
    print(f"New Service ID: ai4bharat/indictasr")
    print(f"Database: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    print("=" * 60)
    print()
    
    success = await update_service_id(db_url)
    
    if success:
        print()
        print("=" * 60)
        print("✅ Service ID updated successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart the model-management-service to refresh caches")
        print("2. Test the service lookup with the new service ID")
        print("3. Update any API calls that reference the old service ID")
    else:
        print()
        print("=" * 60)
        print("❌ Failed to update service ID")
        print("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())



