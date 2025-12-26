# AI4ICore Database Library

Shared database connection management and session factory functionality for AI4ICore microservices.

## Features

- **Async PostgreSQL Connection Management**: Handles async database engine creation and configuration
- **Session Factory**: Provides async session factory for SQLAlchemy
- **Connection Health Checking**: Built-in connection testing and health checks
- **Graceful Cleanup**: Proper connection disposal and cleanup
- **FastAPI Integration**: Dependency injection support for FastAPI routes

## Installation

Install the package in editable mode:

```bash
pip install -e libs/ai4icore_db
```

Or add it to your service's `requirements.txt`:

```
-e ../../libs/ai4icore_db
```

## Usage

### Basic Setup

```python
from ai4icore_db import (
    init_database_connections,
    init_session_factory,
    get_db_session,
    close_database_connections,
)
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI()

@app.on_event("startup")
async def startup():
    # Initialize database connections
    engine = init_database_connections(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        pool_size=20,
        max_overflow=10,
    )
    
    # Initialize session factory
    init_session_factory(engine=engine)

@app.on_event("shutdown")
async def shutdown():
    # Close database connections
    await close_database_connections()

@app.get("/items")
async def get_items(db: AsyncSession = Depends(get_db_session)):
    # Use db session here
    result = await db.execute(text("SELECT * FROM items"))
    return result.fetchall()
```

### Using Environment Variables

The library automatically reads configuration from environment variables:

```python
from ai4icore_db import init_database_connections, init_session_factory

# Reads DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW from environment
engine = init_database_connections()
session_factory = init_session_factory(engine=engine)
```

### Advanced Configuration

```python
from ai4icore_db import create_database_engine, create_session_factory

# Custom engine configuration
engine = create_database_engine(
    database_url="postgresql+asyncpg://user:pass@localhost/db",
    pool_size=30,
    max_overflow=15,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
    connect_args={"timeout": 30, "command_timeout": 30},
)

# Custom session factory
session_factory = create_session_factory(
    engine=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)
```

## API Reference

### Connection Management

- `init_database_connections()`: Initialize and store global database engine
- `create_database_engine()`: Create a new database engine instance
- `get_database_engine()`: Get the global database engine
- `test_database_connection()`: Test database connectivity
- `close_database_connections()`: Close all database connections

### Session Factory

- `init_session_factory()`: Initialize and store global session factory
- `create_session_factory()`: Create a new session factory instance
- `get_session_factory()`: Get the global session factory
- `get_db_session()`: FastAPI dependency for getting database sessions

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection string (default: `postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@postgres:5432/auth_db`)
- `DB_POOL_SIZE`: Connection pool size (default: `20`)
- `DB_MAX_OVERFLOW`: Maximum overflow connections (default: `10`)

## License

MIT

