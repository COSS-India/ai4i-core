"""
Test fixtures and configuration for platform-core-service.
"""

import os

import pytest

# Minimal env overrides so config.py can load without real infra
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PASSWORD", "test")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
