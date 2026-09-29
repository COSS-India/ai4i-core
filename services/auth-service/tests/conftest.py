"""
Test fixtures and configuration.
"""

import os
import pytest
import pytest_asyncio

# Override settings for testing
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("RS256_KEY_DIRECTORY", "/tmp/auth-test-keys")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("PLATFORM_NAME", "Test Platform")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
