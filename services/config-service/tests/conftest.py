"""
Pytest configuration and shared fixtures for config-service tests
"""
import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from ai4icore_env import app_env
from fastapi.testclient import TestClient

TEST_REDIS_URL = app_env.test_redis_url


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    client = redis.from_url(TEST_REDIS_URL, decode_responses=False)
    try:
        await client.flushdb()
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
def test_app():
    from main import app
    return app


@pytest.fixture
def test_client(test_app):
    return TestClient(test_app)


# Pytest configuration
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: Integration tests requiring running services")
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "slow: Tests that take longer than 5 seconds")
