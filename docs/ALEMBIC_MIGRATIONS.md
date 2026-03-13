# Alembic Database Migrations Guide

This guide explains how to use Alembic for database migrations in the AI4I Core platform.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Database Configuration](#database-configuration)
- [Creating Migrations](#creating-migrations)
- [Running Migrations](#running-migrations)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

AI4I Core uses **Alembic** for managing PostgreSQL database schema changes. Alembic provides:

- ✅ **Multi-database support** - Manage 9+ databases from one place
- ✅ **Async SQLAlchemy** - Full async support with asyncpg
- ✅ **Auto-generation** - Generate migrations from SQLAlchemy models
- ✅ **Version control** - Track all schema changes
- ✅ **Rollback support** - Safely undo changes

### Supported Databases

- `auth_db` - Authentication and authorization
- `model_management_db` - Model management and experiments
- `multi_tenant_db` - Multi-tenant management
- `config_db` - Configuration management
- `dashboard_db` - Dashboard data
- `telemetry_db` - Telemetry and observability
- `metrics_db` - Metrics storage
- `alerting_db` - Alerting system
- `ai4i_platform` - Policy engine

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL databases set up
- Environment variables configured (`.env` file)

### Install Alembic

```bash
# From project root
pip install -r infrastructure/databases/requirements.txt

# Or install directly
pip install alembic>=1.12.0
```

## Quick Start

### 1. Check Current Status

```bash
# Check all databases
./scripts/migrate.sh all current

# Check specific database
alembic -x db=auth_db current
```

### 2. Run Migrations

```bash
# Migrate all databases to latest
./scripts/migrate.sh all upgrade

# Migrate specific database
alembic -x db=auth_db upgrade head
```

### 3. Create New Migration

```bash
# Auto-generate from models
alembic -x db=auth_db revision --autogenerate -m "add users table"

# Manual migration
alembic -x db=auth_db revision -m "add new column"
```

## Database Configuration

Alembic reads database connection information from environment variables in your `.env` file.

### Required Environment Variables

```bash
# Auth Database
AUTH_DB_USER=your_user
AUTH_DB_PASSWORD=your_password
AUTH_DB_HOST=localhost
AUTH_DB_PORT=5432
AUTH_DB_NAME=auth_db

# Model Management Database
APP_DB_USER=your_user
APP_DB_PASSWORD=your_password
APP_DB_HOST=localhost
APP_DB_PORT=5432
APP_DB_NAME=model_management_db

# Fallback (used for other databases)
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

### Connection URL Format

Alembic automatically constructs connection URLs:
```
postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}
```

## Creating Migrations

### Auto-Generate from Models

The easiest way to create migrations is to auto-generate them from your SQLAlchemy models:

```bash
# 1. Make changes to your models in services/
# 2. Generate migration
alembic -x db=auth_db revision --autogenerate -m "description"

# 3. Review the generated migration file
# 4. Apply the migration
alembic -x db=auth_db upgrade head
```

**Example:**

```python
# In services/auth-service/models.py
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    # Add new column
    phone_number = Column(String(20), nullable=True)  # NEW
```

```bash
# Generate migration
alembic -x db=auth_db revision --autogenerate -m "add phone_number to users"

# Review generated file in alembic/versions/auth_db/
# Apply migration
alembic -x db=auth_db upgrade head
```

### Manual Migration

For complex changes or data migrations, create manual migrations:

```bash
alembic -x db=auth_db revision -m "add index to users table"
```

Edit the generated file:

```python
def upgrade() -> None:
    op.create_index(
        'idx_users_email',
        'users',
        ['email'],
        unique=True
    )

def downgrade() -> None:
    op.drop_index('idx_users_email', table_name='users')
```

## Running Migrations

### Basic Commands

```bash
# Upgrade to latest (head)
alembic -x db=auth_db upgrade head

# Upgrade by one revision
alembic -x db=auth_db upgrade +1

# Downgrade by one revision
alembic -x db=auth_db downgrade -1

# Downgrade to specific revision
alembic -x db=auth_db downgrade <revision_id>

# Check current revision
alembic -x db=auth_db current

# View history
alembic -x db=auth_db history

# View verbose history
alembic -x db=auth_db history --verbose
```

### Using Helper Script

The `scripts/migrate.sh` script simplifies common operations:

```bash
# Migrate all databases
./scripts/migrate.sh all upgrade

# Migrate specific database
./scripts/migrate.sh auth_db upgrade

# Create migration
./scripts/migrate.sh auth_db revision "add new table"

# Check status
./scripts/migrate.sh auth_db current
```

### Migrate All Databases

```bash
# Using helper script (recommended)
./scripts/migrate.sh all upgrade

# Or manually
for db in auth_db model_management_db multi_tenant_db config_db; do
    alembic -x db=$db upgrade head
done
```

## Best Practices

### 1. Always Review Auto-Generated Migrations

Auto-generated migrations are not always perfect. Always review and test:

```bash
# Generate migration
alembic -x db=auth_db revision --autogenerate -m "changes"

# Review the file in alembic/versions/auth_db/
# Edit if needed
# Test in development
alembic -x db=auth_db upgrade head
```

### 2. Write Reversible Migrations

Always implement both `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20)))

def downgrade() -> None:
    op.drop_column('users', 'phone')
```

### 3. Keep Migrations Small

One logical change per migration:

```python
# Good: Single purpose
def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(255)))

# Bad: Multiple unrelated changes
def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(255)))
    op.create_table('posts', ...)  # Different concern
```

### 4. Use Descriptive Names

Migration filenames should clearly describe the change:

```bash
# Good
alembic -x db=auth_db revision -m "add_email_index_to_users"

# Bad
alembic -x db=auth_db revision -m "update"
```

### 5. Never Edit Applied Migrations

If you need to fix a migration:
1. Create a new migration to correct the issue
2. Or rollback and create a new one (if not in production)

### 6. Test Rollbacks

Always test that `downgrade()` works:

```bash
# Apply migration
alembic -x db=auth_db upgrade head

# Test rollback
alembic -x db=auth_db downgrade -1

# Re-apply
alembic -x db=auth_db upgrade head
```

### 7. Backup Before Production Migrations

```bash
# Backup database
pg_dump -h localhost -U user -d auth_db > backup.sql

# Run migration
alembic -x db=auth_db upgrade head
```

## Troubleshooting

### Connection Errors

**Error**: `sqlalchemy.exc.OperationalError: could not connect to server`

**Solution**:
1. Check database is running: `docker ps` or `systemctl status postgresql`
2. Verify environment variables in `.env`
3. Test connection: `psql -h <host> -U <user> -d <database>`

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'services.auth_service'`

**Solution**:
1. Ensure you're in project root directory
2. Check Python path includes project root
3. Verify service directories exist

### Migration Out of Sync

**Error**: Migration state doesn't match database

**Solution**:
```bash
# Check current state
alembic -x db=auth_db current

# View history
alembic -x db=auth_db history

# Manually stamp to specific revision (if needed)
alembic -x db=auth_db stamp <revision_id>
```

### Auto-Generate Not Detecting Changes

**Possible causes**:
1. Models not imported in `alembic/env.py`
2. Base class not in `DATABASE_METADATA` mapping
3. Changes not saved

**Solution**:
1. Check `alembic/env.py` imports your Base classes
2. Verify models inherit from correct Base class
3. Ensure all model files are saved

### Multiple Heads Error

**Error**: `Multiple heads detected`

**Solution**:
```bash
# View heads
alembic -x db=auth_db heads

# Merge heads
alembic -x db=auth_db merge -m "merge heads" <head1> <head2>
```

## Migration from Custom System

If migrating from the custom migration system in `infrastructure/databases/`:

### Step 1: Generate Initial Migration

```bash
# This creates a migration matching your current database schema
alembic -x db=auth_db revision --autogenerate -m "initial_schema_from_custom_system"
```

### Step 2: Review and Adjust

Review the generated migration file. You may need to:
- Remove duplicate table creations
- Adjust column definitions
- Add missing indexes or constraints

### Step 3: Mark as Applied (if schema already exists)

If your database already has the schema:

```bash
# Mark current migration as applied without running it
alembic -x db=auth_db stamp head
```

### Step 4: Use Alembic Going Forward

All new migrations should use Alembic:

```bash
# Create new migrations with Alembic
alembic -x db=auth_db revision --autogenerate -m "new feature"
```

## CI/CD Integration

### Docker Compose

Add to your `docker-compose.yml`:

```yaml
services:
  auth-service:
    command: >
      sh -c "alembic -x db=auth_db upgrade head && uvicorn main:app --host 0.0.0.0"
```

### Deployment Script

```bash
#!/bin/bash
# deploy.sh

# Run migrations
./scripts/migrate.sh all upgrade

# Start services
docker-compose up -d
```

### GitHub Actions / GitLab CI

```yaml
- name: Run Database Migrations
  run: |
    pip install -r infrastructure/databases/requirements.txt
    ./scripts/migrate.sh all upgrade
```

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Project README](../README.md)
- [Alembic README](../alembic/README.md)

## Support

For issues:
1. Check this guide
2. Review `alembic/README.md`
3. Check Alembic documentation
4. Review project issues
