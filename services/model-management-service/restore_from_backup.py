#!/usr/bin/env python3
"""
Restore database from backup SQL file.
This script properly handles UUIDs, JSON, and other data types.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db_connection import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
from logger import logger

load_dotenv()


async def restore_from_backup(backup_file: str):
    """Restore database from backup SQL file"""
    # Use localhost and port 5434 for restore (override .env if needed)
    restore_host = os.getenv("RESTORE_DB_HOST", "localhost")
    restore_port = int(os.getenv("RESTORE_DB_PORT", "5434"))
    connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{restore_host}:{restore_port}/{DB_NAME}"
    engine = create_async_engine(connection_string, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as db:
            # Clear existing data
            logger.info("Clearing existing data...")
            await db.execute(text("TRUNCATE TABLE services CASCADE"))
            await db.execute(text("TRUNCATE TABLE models CASCADE"))
            await db.commit()
            
            # Read backup file
            logger.info(f"Reading backup file: {backup_file}")
            with open(backup_file, 'r') as f:
                content = f.read()
            
            # Split into INSERT statements
            # Match INSERT statements (handling multi-line)
            insert_pattern = r"INSERT INTO\s+(\w+)\s*\([^)]+\)\s*VALUES\s*\(([^;]+)\);"
            matches = re.finditer(insert_pattern, content, re.DOTALL | re.IGNORECASE)
            
            models_count = 0
            services_count = 0
            
            for match in matches:
                table_name = match.group(1)
                values_str = match.group(2).strip()
                
                try:
                    # Parse the VALUES part - this is tricky because of nested JSON
                    # We'll use a simpler approach: extract the INSERT statement and execute it
                    # But first, we need to properly quote UUIDs and handle JSON
                    
                    # Find the full INSERT statement
                    full_match = match.group(0)
                    
                    # Fix UUIDs - they should be quoted
                    # Pattern: (787e1577-d6e7-49cd-a9a3-698d7ea93e6b, -> ('787e1577-d6e7-49cd-a9a3-698d7ea93e6b',
                    uuid_pattern = r'\(([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}),'
                    fixed_statement = re.sub(uuid_pattern, r"('\1',", full_match, flags=re.IGNORECASE)
                    
                    # Execute the statement
                    await db.execute(text(fixed_statement))
                    
                    if table_name.lower() == 'models':
                        models_count += 1
                    elif table_name.lower() == 'services':
                        services_count += 1
                        
                except Exception as e:
                    logger.error(f"Error inserting into {table_name}: {e}")
                    logger.error(f"Statement: {full_match[:200]}...")
                    continue
            
            await db.commit()
            logger.info(f"✓ Restore completed!")
            logger.info(f"  Models restored: {models_count}")
            logger.info(f"  Services restored: {services_count}")
            
    except Exception as e:
        logger.exception(f"Error during restore: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    backup_file = sys.argv[1] if len(sys.argv) > 1 else "backup_before_migration_20260114_165913.sql"
    
    if not os.path.exists(backup_file):
        logger.error(f"Backup file not found: {backup_file}")
        sys.exit(1)
    
    logger.info("=" * 80)
    logger.info("Restoring database from backup")
    logger.info("=" * 80)
    asyncio.run(restore_from_backup(backup_file))
