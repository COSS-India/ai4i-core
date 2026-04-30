"""
Pytest configuration and shared fixtures for feature flag tests
"""
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest
import pytest_asyncio
import redis.asyncio as redis
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models.database_models import Base, FeatureFlag, FeatureFlagEvaluation
from repositories.feature_flag_repository import FeatureFlagRepository
from services.feature_flag_service import FeatureFlagService
from providers.unleash_provider import UnleashFeatureProvider
from openfeature.evaluation_context import EvaluationContext
from openfeature import api as openfeature_api

# Test database URL
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://dhruva_user:dhruva_secure_password_2024@localhost:5432/config_db_test"
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/2")

# Create async engine for testing
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for testing."""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
    
    # Clean up tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create Redis client for cache testing."""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=False)
    try:
        # Clear test database
        await client.flushdb()
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer"""
    producer = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_unleash_client():
    """Mock Unleash client"""
    client = Mock()
    client.is_enabled = Mock(return_value=True)
    client.get_variant = Mock(return_value=None)
    client.initialize_client = Mock()
    client.destroy = Mock()
    return client


@pytest.fixture
def mock_openfeature_client():
    """Mock OpenFeature client"""
    client = Mock()
    
    # Mock boolean details
    boolean_details = Mock()
    boolean_details.value = True
    boolean_details.reason = "TARGETING_MATCH"
    boolean_details.flag_key = "test-flag"
    client.get_boolean_details = Mock(return_value=boolean_details)
    
    # Mock string details
    string_details = Mock()
    string_details.value = "variant-a"
    string_details.reason = "TARGETING_MATCH"
    string_details.flag_key = "test-flag"
    string_details.variant = "variant-a"
    client.get_string_details = Mock(return_value=string_details)
    
    # Mock integer details
    integer_details = Mock()
    integer_details.value = 42
    integer_details.reason = "TARGETING_MATCH"
    integer_details.flag_key = "test-flag"
    client.get_integer_details = Mock(return_value=integer_details)
    
    # Mock float details
    float_details = Mock()
    float_details.value = 3.14
    float_details.reason = "TARGETING_MATCH"
    float_details.flag_key = "test-flag"
    client.get_float_details = Mock(return_value=float_details)
    
    # Mock object details
    object_details = Mock()
    object_details.value = {"key": "value"}
    object_details.reason = "TARGETING_MATCH"
    object_details.flag_key = "test-flag"
    object_details.variant = "variant-a"
    client.get_object_details = Mock(return_value=object_details)
    
    return client


@pytest.fixture
def feature_flag_repository(test_db_session):
    """Create feature flag repository"""
    return FeatureFlagRepository(test_db_session)


@pytest.fixture
def feature_flag_service(
    feature_flag_repository,
    redis_client,
    mock_kafka_producer,
    mock_openfeature_client,
):
    """Create feature flag service with mocked dependencies"""
    return FeatureFlagService(
        repository=feature_flag_repository,
        redis_client=redis_client,
        kafka_producer=mock_kafka_producer,
        openfeature_client=mock_openfeature_client,
        kafka_topic="test-topic",
        cache_ttl=300,
        unleash_url="http://unleash:4242/api",
        unleash_api_token="test-token",
    )


@pytest.fixture
def unleash_provider(mock_unleash_client):
    """Create Unleash provider with mocked client"""
    provider = UnleashFeatureProvider(
        url="http://unleash:4242/api",
        app_name="test-app",
        instance_id="test-1",
        api_token="test-token",
    )
    provider.client = mock_unleash_client
    provider._initialized = True
    return provider


@pytest.fixture
def test_app():
    """Create FastAPI test app"""
    from main import app
    return app


@pytest.fixture
def test_client(test_app):
    """Create FastAPI test client"""
    return TestClient(test_app)


# Pytest configuration
pytest_plugins = ["pytest_asyncio"]

# Custom markers
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: Integration tests requiring running services")
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "unleash: Tests requiring Unleash server")
    config.addinivalue_line("markers", "slow: Tests that take longer than 5 seconds")

