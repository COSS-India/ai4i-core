#!/usr/bin/env python3
"""
Restore database from backup SQL file using SQLAlchemy models.
This properly handles all data types including UUIDs, JSON, dates, etc.
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
from models.db_models import Model, Service

load_dotenv()


def parse_insert_statement(insert_line: str):
    """Parse an INSERT statement and extract table name, columns, and values"""
    # Match: INSERT INTO table_name (col1, col2, ...) VALUES (val1, val2, ...);
    pattern = r"INSERT INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\);"
    match = re.search(pattern, insert_line, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return None
    
    table_name = match.group(1).strip()
    columns_str = match.group(2).strip()
    values_str = match.group(3).strip()
    
    # Parse columns
    columns = [col.strip() for col in columns_str.split(',')]
    
    # Parse values - this is tricky because of nested structures
    # We'll use a simple approach: split by comma, but be careful with nested structures
    values = []
    current_value = ""
    depth = 0
    in_string = False
    string_char = None
    
    for char in values_str:
        if char in ("'", '"') and (not current_value or current_value[-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None
            current_value += char
        elif char == '{' and not in_string:
            depth += 1
            current_value += char
        elif char == '}' and not in_string:
            depth -= 1
            current_value += char
        elif char == ',' and depth == 0 and not in_string:
            values.append(current_value.strip())
            current_value = ""
        else:
            current_value += char
    
    if current_value:
        values.append(current_value.strip())
    
    return {
        'table': table_name,
        'columns': columns,
        'values': values
    }


def parse_value(value_str: str, column_name: str):
    """Parse a single value from the INSERT statement"""
    value_str = value_str.strip()
    
    if value_str.upper() == 'NULL':
        return None
    
    # Check if it's a UUID (unquoted UUID pattern)
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    if re.match(uuid_pattern, value_str, re.IGNORECASE):
        return value_str
    
    # Check if it's a quoted string
    if (value_str.startswith("'") and value_str.endswith("'")) or \
       (value_str.startswith('"') and value_str.endswith('"')):
        # Remove quotes and unescape
        unquoted = value_str[1:-1].replace("''", "'")
        return unquoted
    
    # Check if it's JSON (starts with { or [)
    if value_str.startswith('{') or value_str.startswith('['):
        try:
            return json.loads(value_str)
        except:
            return value_str
    
    # Check if it's a number
    try:
        if '.' in value_str:
            return float(value_str)
        else:
            return int(value_str)
    except:
        pass
    
    # Check if it's a boolean
    if value_str.upper() == 'TRUE':
        return True
    if value_str.upper() == 'FALSE':
        return False
    
    # Check if it's a datetime
    # Try to parse common datetime formats
    datetime_patterns = [
        r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
    ]
    for pattern in datetime_patterns:
        if re.match(pattern, value_str):
            try:
                # Try parsing with timezone
                return datetime.fromisoformat(value_str.replace('+00:00', ''))
            except:
                pass
    
    return value_str


async def restore_from_backup(backup_file: str):
    """Restore database from backup SQL file"""
    # Use localhost and port 5434 for restore
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
                lines = f.readlines()
            
            # First pass: collect all INSERT statements
            model_statements = []
            service_statements = []
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('--'):
                    continue
                
                if not line.upper().startswith('INSERT INTO'):
                    continue
                
                parsed = parse_insert_statement(line)
                if not parsed:
                    continue
                
                if parsed['table'].lower() == 'models':
                    model_statements.append(parsed)
                elif parsed['table'].lower() == 'services':
                    service_statements.append(parsed)
            
            # Restore models first
            logger.info(f"Restoring {len(model_statements)} models...")
            models_count = 0
            errors = 0
            
            for parsed in model_statements:
                try:
                    # Build a dict from columns and values
                    data = {}
                    for col, val_str in zip(parsed['columns'], parsed['values']):
                        data[col] = parse_value(val_str, col)
                    
                    # Create Model instance
                    model = Model(**data)
                    db.add(model)
                    models_count += 1
                    
                    # Commit in batches
                    if models_count % 10 == 0:
                        await db.commit()
                        
                except Exception as e:
                    logger.error(f"Error inserting model: {e}")
                    errors += 1
                    await db.rollback()
                    continue
            
            # Commit remaining models
            await db.commit()
            logger.info(f"  Models restored: {models_count}")
            
            # Now restore services
            logger.info(f"Restoring {len(service_statements)} services...")
            services_count = 0
            
            for parsed in service_statements:
                try:
                    # Build a dict from columns and values
                    data = {}
                    for col, val_str in zip(parsed['columns'], parsed['values']):
                        data[col] = parse_value(val_str, col)
                    
                    # Create Service instance
                    service = Service(**data)
                    db.add(service)
                    services_count += 1
                    
                    # Commit in batches
                    if services_count % 10 == 0:
                        await db.commit()
                        
                except Exception as e:
                    logger.error(f"Error inserting service: {e}")
                    errors += 1
                    await db.rollback()
                    continue
            
            # Final commit
            await db.commit()
            
            logger.info(f"✓ Restore completed!")
            logger.info(f"  Models restored: {models_count}")
            logger.info(f"  Services restored: {services_count}")
            if errors > 0:
                logger.warning(f"  Errors: {errors}")
            
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
