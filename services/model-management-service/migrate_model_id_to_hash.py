#!/usr/bin/env python3
"""
Migration script to convert model_id from user-entered string to hash of (model_name, version).

Steps:
1. Copy current model_id value to name field (if name is empty or different)
2. Generate new model_id as hash of (name, version)
3. Update both models and services tables

This script should be run before deploying the new code that generates model_id from hash.
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


def generate_model_id(model_name: str, version: str) -> str:
    """
    Generate a unique model_id hash from model_name and version.
    This matches the function in db_operations.py
    """
    hash_input = f"{model_name}:{version}".encode('utf-8')
    hash_obj = hashlib.sha256(hash_input)
    return hash_obj.hexdigest()[:32]


async def migrate_models_table(db: AsyncSession) -> Tuple[int, int, Dict[str, str]]:
    """
    Migrate the models table:
    1. Copy model_id to name if name is empty or different
    2. Generate new model_id from hash(name, version)
    3. Update the model_id field
    
    Returns:
        Tuple of (models_updated, errors, model_id_mapping)
    """
    models_updated = 0
    errors = 0
    constraint_dropped = False
    
    try:
        # Temporarily disable foreign key constraint once at the beginning
        # This allows us to update both models and services without constraint violations
        try:
            # Try to find and drop the foreign key constraint
            constraint_result = await db.execute(text("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'services' 
                AND constraint_type = 'FOREIGN KEY'
                AND (constraint_name LIKE '%model%' OR constraint_name LIKE '%fkey%')
            """))
            constraints = constraint_result.fetchall()
            for constraint in constraints:
                constraint_name = constraint[0]
                await db.execute(text(f"ALTER TABLE services DROP CONSTRAINT IF EXISTS {constraint_name}"))
                logger.info(f"Temporarily disabled foreign key constraint: {constraint_name}")
                constraint_dropped = True
            # Commit the constraint drop
            await db.commit()
        except Exception as e:
            logger.warning(f"Could not disable foreign key constraint (may not exist or already dropped): {e}")
            # Try to continue anyway
        
        # Fetch all models
        result = await db.execute(text("SELECT id, model_id, version, name FROM models"))
        models = result.fetchall()
        
        logger.info(f"Found {len(models)} models to migrate")
        
        # Track (old_model_id, version) -> new_model_id mapping for services table update
        # Using tuple as key to handle same old_model_id with different versions
        model_id_mapping: Dict[Tuple[str, str], str] = {}
        
        for model in models:
            model_uuid = model[0]
            old_model_id = model[1]
            version = model[2]
            current_name = model[3]
            
            try:
                # STEP 1: Copy current model_id value to name field (FIRST STEP - REQUIRED)
                # This preserves the original model_id value in the name field before generating hash
                new_name = old_model_id
                if not current_name or current_name.strip() == "":
                    logger.info(f"Model {model_uuid}: Step 1 - Copying model_id '{old_model_id}' to name field (name was empty)")
                else:
                    logger.info(f"Model {model_uuid}: Step 1 - Copying model_id '{old_model_id}' to name field (replacing '{current_name}')")
                
                # Update name field first (before checking duplicates or generating hash)
                await db.execute(
                    text("UPDATE models SET name = :name WHERE id = :id"),
                    {"name": new_name, "id": model_uuid}
                )
                
                # Check for duplicate (name, version) combinations and make name unique if needed
                # This happens after copying model_id to name
                check_dup_result = await db.execute(
                    text("SELECT COUNT(*) FROM models WHERE name = :name AND version = :version AND id != :id"),
                    {"name": new_name, "version": version, "id": model_uuid}
                )
                dup_count = check_dup_result.scalar()
                if dup_count > 0:
                    # Make name unique by appending a suffix (using UUID to ensure uniqueness)
                    unique_suffix = str(model_uuid)[:8]
                    new_name = f"{new_name}_{unique_suffix}"
                    logger.warning(
                        f"Model {model_uuid}: Duplicate (name, version) detected after copying model_id. "
                        f"Making name unique: '{new_name}'"
                    )
                    # Update name again with unique value
                    await db.execute(
                        text("UPDATE models SET name = :name WHERE id = :id"),
                        {"name": new_name, "id": model_uuid}
                    )
                
                # Check if model_id is already in hash format (32-character hex)
                import re
                is_already_hashed = bool(re.match(r'^[a-f0-9]{32}$', old_model_id))
                
                if is_already_hashed:
                    # Check if it matches the expected hash
                    expected_hash = generate_model_id(new_name, version)
                    if old_model_id == expected_hash:
                        logger.info(f"Model {model_uuid}: model_id already in correct hash format, skipping")
                        model_id_mapping[(old_model_id, version)] = old_model_id
                        continue
                    else:
                        logger.warning(
                            f"Model {model_uuid}: model_id is hashed but doesn't match expected hash. "
                            f"Expected: {expected_hash}, Current: {old_model_id}. Will update."
                        )
                
                # Step 2: Generate new model_id from hash(name, version)
                new_model_id = generate_model_id(new_name, version)
                
                if old_model_id == new_model_id and not is_already_hashed:
                    logger.info(f"Model {model_uuid}: model_id already matches hash, skipping")
                    # Still add to mapping in case services need it
                    model_id_mapping[(old_model_id, version)] = new_model_id
                    continue
                
                # Step 3: Update the model
                # First, check if the new model_id already exists (shouldn't happen, but safety check)
                check_result = await db.execute(
                    text("SELECT id FROM models WHERE model_id = :new_model_id"),
                    {"new_model_id": new_model_id}
                )
                if check_result.fetchone():
                    logger.error(
                        f"Model {model_uuid}: New model_id '{new_model_id}' already exists! "
                        f"This indicates a hash collision. Skipping."
                    )
                    errors += 1
                    continue
                
                # STEP 2: Generate new model_id from hash(name, version)
                # (Name has already been updated in Step 1)
                
                # First, update all services that reference this model_id to use the new model_id
                # (Constraint is already disabled at the beginning)
                services_updated = await db.execute(
                    text("""
                        UPDATE services 
                        SET model_id = :new_model_id 
                        WHERE model_id = :old_model_id AND model_version = :version
                    """),
                    {"new_model_id": new_model_id, "old_model_id": old_model_id, "version": version}
                )
                if services_updated.rowcount > 0:
                    logger.info(f"Model {model_uuid}: Updated {services_updated.rowcount} service(s) to use new model_id")
                
                # Now update model_id in models table
                await db.execute(
                    text("UPDATE models SET model_id = :new_model_id WHERE id = :id"),
                    {"new_model_id": new_model_id, "id": model_uuid}
                )
                
                # Store mapping using (old_model_id, version) as key
                model_id_mapping[(old_model_id, version)] = new_model_id
                models_updated += 1
                
                logger.info(
                    f"Model {model_uuid}: Updated model_id from '{old_model_id}' to '{new_model_id}' "
                    f"(name: '{new_name}', version: '{version}')"
                )
                
            except Exception as e:
                logger.error(f"Error migrating model {model_uuid}: {e}")
                # Rollback this model's transaction and continue
                await db.rollback()
                # Re-fetch models after rollback
                result = await db.execute(text("SELECT id, model_id, version, name FROM models"))
                models = result.fetchall()
                errors += 1
                continue
        
        # Commit all changes first
        await db.commit()
        logger.info(f"Models table migration complete: {models_updated} updated, {errors} errors")
        
        return models_updated, errors, model_id_mapping, constraint_dropped
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during models table migration: {e}")
        raise


async def re_enable_constraint(db: AsyncSession, constraint_dropped: bool):
    """Re-enable foreign key constraint if it was disabled"""
    if constraint_dropped:
        try:
            # Try to recreate the foreign key constraint
            # Note: The actual constraint name and definition may vary
            await db.execute(text("""
                ALTER TABLE services 
                ADD CONSTRAINT services_model_id_fkey 
                FOREIGN KEY (model_id, model_version) 
                REFERENCES models(model_id, version)
            """))
            await db.commit()
            logger.info("Re-enabled foreign key constraint")
        except Exception as e:
            # Constraint might already exist or have a different definition
            logger.warning(f"Could not recreate constraint (might already exist or need manual recreation): {e}")
            await db.rollback()
    else:
        logger.info("No constraint was dropped, skipping re-enable")


async def migrate_services_table(db: AsyncSession, model_id_mapping: Dict[Tuple[str, str], str]) -> Tuple[int, int]:
    """
    Migrate the services table:
    Update model_id references to use the new hashed model_id values
    
    Args:
        model_id_mapping: Dictionary mapping (old_model_id, version) tuple to new model_id
    
    Returns:
        Tuple of (services_updated, errors)
    """
    services_updated = 0
    errors = 0
    
    try:
        # Fetch all services with their model_id and model_version
        result = await db.execute(
            text("SELECT id, service_id, model_id, model_version FROM services")
        )
        services = result.fetchall()
        
        logger.info(f"Found {len(services)} services to migrate")
        
        for service in services:
            service_uuid = service[0]
            service_id = service[1]
            old_model_id = service[2]
            model_version = service[3]
            
            try:
                # Look up the new model_id using (old_model_id, version) as key
                mapping_key = (old_model_id, model_version)
                if mapping_key not in model_id_mapping:
                    # Try to find the model by old_model_id and version to generate new hash
                    model_result = await db.execute(
                        text("SELECT name FROM models WHERE model_id = :model_id AND version = :version"),
                        {"model_id": old_model_id, "version": model_version}
                    )
                    model_row = model_result.fetchone()
                    
                    if model_row:
                        model_name = model_row[0]
                        new_model_id = generate_model_id(model_name, model_version)
                        model_id_mapping[mapping_key] = new_model_id
                        logger.info(
                            f"Service {service_id}: Generated new model_id '{new_model_id}' from "
                            f"model lookup (name: '{model_name}', version: '{model_version}')"
                        )
                    else:
                        logger.warning(
                            f"Service {service_id}: Could not find model with model_id '{old_model_id}' "
                            f"and version '{model_version}'. Skipping."
                        )
                        errors += 1
                        continue
                
                new_model_id = model_id_mapping[mapping_key]
                
                if old_model_id == new_model_id:
                    logger.info(f"Service {service_id}: model_id already matches, skipping")
                    continue
                
                # Update the service
                await db.execute(
                    text("UPDATE services SET model_id = :new_model_id WHERE id = :id"),
                    {"new_model_id": new_model_id, "id": service_uuid}
                )
                
                services_updated += 1
                logger.info(
                    f"Service {service_id}: Updated model_id from '{old_model_id}' to '{new_model_id}'"
                )
                
            except Exception as e:
                logger.error(f"Error migrating service {service_id}: {e}")
                errors += 1
                continue
        
        # Commit all changes
        await db.commit()
        logger.info(f"Services table migration complete: {services_updated} updated, {errors} errors")
        
        return services_updated, errors
        
    except Exception as e:
        await db.rollback()
        logger.exception(f"Error during services table migration: {e}")
        raise


async def verify_migration(db: AsyncSession) -> bool:
    """
    Verify that all model_ids are now hashes and match (name, version) combinations.
    
    Returns:
        True if verification passes, False otherwise
    """
    try:
        # Check that all model_ids are 32-character hex strings (hash format)
        result = await db.execute(
            text("""
                SELECT id, model_id, name, version 
                FROM models 
                WHERE LENGTH(model_id) != 32 
                   OR model_id !~ '^[a-f0-9]{32}$'
            """)
        )
        invalid_models = result.fetchall()
        
        if invalid_models:
            logger.error(f"Found {len(invalid_models)} models with invalid model_id format:")
            for model in invalid_models:
                logger.error(f"  Model {model[0]}: model_id='{model[1]}', name='{model[2]}', version='{model[3]}'")
            return False
        
        # Verify that model_id matches hash(name, version) for all models
        result = await db.execute(
            text("SELECT id, model_id, name, version FROM models")
        )
        models = result.fetchall()
        
        mismatches = []
        for model in models:
            model_id = model[1]
            name = model[2]
            version = model[3]
            expected_model_id = generate_model_id(name, version)
            
            if model_id != expected_model_id:
                mismatches.append({
                    "id": model[0],
                    "current_model_id": model_id,
                    "expected_model_id": expected_model_id,
                    "name": name,
                    "version": version
                })
        
        if mismatches:
            logger.error(f"Found {len(mismatches)} models where model_id doesn't match hash(name, version):")
            for mismatch in mismatches:
                logger.error(
                    f"  Model {mismatch['id']}: model_id='{mismatch['current_model_id']}', "
                    f"expected='{mismatch['expected_model_id']}', name='{mismatch['name']}', "
                    f"version='{mismatch['version']}'"
                )
            return False
        
        logger.info("✓ Verification passed: All model_ids are valid hashes matching (name, version)")
        return True
        
    except Exception as e:
        logger.exception(f"Error during verification: {e}")
        return False


async def main():
    """Main migration function"""
    logger.info("=" * 80)
    logger.info("Starting model_id migration: Converting to hash of (name, version)")
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
            # Step 1: Migrate models table
            logger.info("\n" + "=" * 80)
            logger.info("Step 1: Migrating models table")
            logger.info("=" * 80)
            models_updated, models_errors, model_id_mapping, constraint_dropped = await migrate_models_table(db)
            
            # Step 2: Migrate services table
            logger.info("\n" + "=" * 80)
            logger.info("Step 2: Migrating services table")
            logger.info("=" * 80)
            services_updated, services_errors = await migrate_services_table(db, model_id_mapping)
            
            # Step 3: Re-enable foreign key constraint
            logger.info("\n" + "=" * 80)
            logger.info("Step 3: Re-enabling foreign key constraint")
            logger.info("=" * 80)
            await re_enable_constraint(db, constraint_dropped)
            
            # Step 4: Verify migration
            logger.info("\n" + "=" * 80)
            logger.info("Step 4: Verifying migration")
            logger.info("=" * 80)
            verification_passed = await verify_migration(db)
            
            # Summary
            logger.info("\n" + "=" * 80)
            logger.info("Migration Summary")
            logger.info("=" * 80)
            logger.info(f"Models updated: {models_updated}")
            logger.info(f"Models errors: {models_errors}")
            logger.info(f"Services updated: {services_updated}")
            logger.info(f"Services errors: {services_errors}")
            logger.info(f"Verification: {'PASSED' if verification_passed else 'FAILED'}")
            
            if models_errors > 0 or services_errors > 0 or not verification_passed:
                logger.error("\n⚠️  Migration completed with errors. Please review the logs above.")
                sys.exit(1)
            else:
                logger.info("\n✓ Migration completed successfully!")
                sys.exit(0)
                
        except Exception as e:
            logger.exception(f"Fatal error during migration: {e}")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
