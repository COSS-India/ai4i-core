#!/usr/bin/env python3
"""
Migration script to convert service_id from user-entered string to hash of (model_name, model_version, service_name).

Steps:
1. For each service, look up the associated model to get model_name
2. Generate new service_id as hash of (model_name, model_version, service_name)
3. Update the service_id in the services table

This script should be run before deploying the new code that generates service_id from hash.
Run the SQL migration script (12-service-id-hash-migration.sql) after this Python script.
"""

import asyncio
import hashlib
import os
import sys
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Add the service directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from db_connection import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
from logger import logger

load_dotenv()


def generate_service_id(model_name: str, model_version: str, service_name: str) -> str:
    """
    Generate a unique service_id hash from model_name, model_version, and service_name.
    This matches the function in db_operations.py
    """
    # Normalize inputs: strip whitespace and convert to lowercase for consistency
    normalized_model_name = model_name.strip().lower()
    normalized_model_version = model_version.strip().lower()
    normalized_service_name = service_name.strip().lower()
    
    hash_input = f"{normalized_model_name}:{normalized_model_version}:{normalized_service_name}".encode('utf-8')
    hash_obj = hashlib.sha256(hash_input)
    return hash_obj.hexdigest()[:32]


async def migrate_services_table(db: AsyncSession) -> Tuple[int, int, Dict[str, str]]:
    """
    Migrate the services table:
    1. For each service, look up the model to get model_name
    2. Generate new service_id from hash(model_name, model_version, service_name)
    3. Update the service_id field
    
    Returns:
        Tuple of (services_updated, errors, service_id_mapping)
    """
    services_updated = 0
    errors = 0
    service_id_mapping: Dict[str, str] = {}  # old_service_id -> new_service_id
    
    try:
        # Fetch all services with their model reference
        result = await db.execute(text("""
            SELECT s.id, s.service_id, s.name, s.model_id, s.model_version, m.name as model_name
            FROM services s
            LEFT JOIN models m ON s.model_id = m.model_id AND s.model_version = m.version
        """))
        services = result.fetchall()
        
        logger.info(f"Found {len(services)} services to migrate")
        
        for service in services:
            service_uuid = service[0]
            old_service_id = service[1]
            service_name = service[2]
            model_id = service[3]
            model_version = service[4]
            model_name = service[5]
            
            try:
                if not model_name:
                    logger.warning(
                        f"Service {service_uuid}: Could not find model with model_id '{model_id}' "
                        f"and version '{model_version}'. Skipping."
                    )
                    errors += 1
                    continue
                
                # Check if service_id is already in hash format (32-character hex)
                import re
                is_already_hashed = bool(re.match(r'^[a-f0-9]{32}$', old_service_id))
                
                if is_already_hashed:
                    # Check if it matches the expected hash
                    expected_hash = generate_service_id(model_name, model_version, service_name)
                    if old_service_id == expected_hash:
                        logger.info(f"Service {service_uuid}: service_id already in correct hash format, skipping")
                        service_id_mapping[old_service_id] = old_service_id
                        continue
                    else:
                        logger.warning(
                            f"Service {service_uuid}: service_id is hashed but doesn't match expected hash. "
                            f"Expected: {expected_hash}, Current: {old_service_id}. Will update."
                        )
                
                # Generate new service_id from hash(model_name, model_version, service_name)
                new_service_id = generate_service_id(model_name, model_version, service_name)
                
                if old_service_id == new_service_id:
                    logger.info(f"Service {service_uuid}: service_id already matches hash, skipping")
                    service_id_mapping[old_service_id] = new_service_id
                    continue
                
                # Check if the new service_id already exists (safety check for hash collisions)
                check_result = await db.execute(
                    text("SELECT id FROM services WHERE service_id = :new_service_id AND id != :id"),
                    {"new_service_id": new_service_id, "id": service_uuid}
                )
                if check_result.fetchone():
                    logger.error(
                        f"Service {service_uuid}: New service_id '{new_service_id}' already exists! "
                        f"This indicates a hash collision or duplicate (model_name, model_version, service_name). Skipping."
                    )
                    errors += 1
                    continue
                
                # Update service_id in services table
                await db.execute(
                    text("UPDATE services SET service_id = :new_service_id WHERE id = :id"),
                    {"new_service_id": new_service_id, "id": service_uuid}
                )
                
                # Store mapping
                service_id_mapping[old_service_id] = new_service_id
                services_updated += 1
                
                logger.info(
                    f"Service {service_uuid}: Updated service_id from '{old_service_id}' to '{new_service_id}' "
                    f"(model_name: '{model_name}', model_version: '{model_version}', service_name: '{service_name}')"
                )
                
            except Exception as e:
                logger.error(f"Error migrating service {service_uuid}: {e}")
                errors += 1
                continue
        
        # Commit all changes
        await db.commit()
        logger.info(f"Services table migration complete: {services_updated} updated, {errors} errors")
        
        return services_updated, errors, service_id_mapping
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during services table migration: {e}")
        raise


async def verify_migration(db: AsyncSession) -> bool:
    """
    Verify that all service_ids are now hashes and match (model_name, model_version, service_name) combinations.
    
    Returns:
        True if verification passes, False otherwise
    """
    try:
        # Check that all service_ids are 32-character hex strings (hash format)
        result = await db.execute(
            text("""
                SELECT id, service_id, name, model_id, model_version 
                FROM services 
                WHERE LENGTH(service_id) != 32 
                   OR service_id !~ '^[a-f0-9]{32}$'
            """)
        )
        invalid_services = result.fetchall()
        
        if invalid_services:
            logger.error(f"Found {len(invalid_services)} services with invalid service_id format:")
            for service in invalid_services:
                logger.error(f"  Service {service[0]}: service_id='{service[1]}', name='{service[2]}', model_id='{service[3]}', model_version='{service[4]}'")
            return False
        
        # Verify that service_id matches hash(model_name, model_version, service_name) for all services
        result = await db.execute(text("""
            SELECT s.id, s.service_id, s.name, s.model_id, s.model_version, m.name as model_name
            FROM services s
            LEFT JOIN models m ON s.model_id = m.model_id AND s.model_version = m.version
        """))
        services = result.fetchall()
        
        mismatches = []
        for service in services:
            service_id = service[1]
            service_name = service[2]
            model_name = service[5]
            model_version = service[4]
            
            if not model_name:
                logger.warning(f"Service {service[0]}: Could not find associated model, skipping verification")
                continue
            
            expected_service_id = generate_service_id(model_name, model_version, service_name)
            
            if service_id != expected_service_id:
                mismatches.append({
                    "id": service[0],
                    "current_service_id": service_id,
                    "expected_service_id": expected_service_id,
                    "service_name": service_name,
                    "model_name": model_name,
                    "model_version": model_version
                })
        
        if mismatches:
            logger.error(f"Found {len(mismatches)} services where service_id doesn't match hash(model_name, model_version, service_name):")
            for mismatch in mismatches:
                logger.error(
                    f"  Service {mismatch['id']}: service_id='{mismatch['current_service_id']}', "
                    f"expected='{mismatch['expected_service_id']}', service_name='{mismatch['service_name']}', "
                    f"model_name='{mismatch['model_name']}', model_version='{mismatch['model_version']}'"
                )
            return False
        
        logger.info("✓ Verification passed: All service_ids are valid hashes matching (model_name, model_version, service_name)")
        return True
        
    except Exception as e:
        logger.exception(f"Error during verification: {e}")
        return False


async def main():
    """Main migration function"""
    logger.info("=" * 80)
    logger.info("Starting service_id migration: Converting to hash of (model_name, model_version, service_name)")
    logger.info("=" * 80)
    
    # Create database connection
    # Use localhost:5434 for migration (override .env if needed)
    migration_host = os.getenv("MIGRATION_DB_HOST", "localhost")
    migration_port = int(os.getenv("MIGRATION_DB_PORT", "5434"))
    connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{migration_host}:{migration_port}/{DB_NAME}"
    logger.info(f"Connecting to database: {migration_host}:{migration_port}")
    engine = create_async_engine(connection_string, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # Step 1: Migrate services table
            logger.info("\n" + "=" * 80)
            logger.info("Step 1: Migrating services table")
            logger.info("=" * 80)
            services_updated, errors, service_id_mapping = await migrate_services_table(db)
            
            # Step 2: Verify migration
            logger.info("\n" + "=" * 80)
            logger.info("Step 2: Verifying migration")
            logger.info("=" * 80)
            verification_passed = await verify_migration(db)
            
            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("Migration Summary")
            logger.info("=" * 80)
            logger.info(f"Services updated: {services_updated}")
            logger.info(f"Errors: {errors}")
            logger.info(f"Verification: {'PASSED' if verification_passed else 'FAILED'}")
            
            if errors > 0 or not verification_passed:
                logger.error("\n⚠️  Migration completed with errors. Please review the logs above.")
                sys.exit(1)
            else:
                logger.info("\n✓ Migration completed successfully!")
                logger.info("\nNext steps:")
                logger.info("1. Run the SQL migration script: 12-service-id-hash-migration.sql")
                logger.info("   This will add the unique constraint on (model_id, model_version, name)")
                sys.exit(0)
                
        except Exception as e:
            logger.exception(f"Fatal error during migration: {e}")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
