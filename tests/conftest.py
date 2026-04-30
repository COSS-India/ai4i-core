"""
Pytest configuration and shared fixtures for all integration tests.
"""
import asyncio
import base64
import os
from typing import AsyncGenerator, Generator

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Test database URL - should be different from production
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://dhruva_user:dhruva_password@localhost:5432/auth_db")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

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
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture(scope="session")
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create httpx.AsyncClient for API testing."""
    async with httpx.AsyncClient(
        base_url="http://localhost:8080",
        headers={"Content-Type": "application/json"},
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def test_api_key(test_db_session: AsyncSession) -> str:
    """Create test API key in database."""
    # This would typically create a test API key in the database
    # For now, return a mock API key for testing
    return "test_api_key_12345"


@pytest.fixture(scope="function")
async def authenticated_client(test_api_key: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create httpx.AsyncClient with Authorization header."""
    async with httpx.AsyncClient(
        base_url="http://localhost:8080",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {test_api_key}"
        },
        timeout=30.0
    ) as client:
        yield client


@pytest.fixture(scope="session")
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create Redis client for cache testing."""
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.close()


@pytest.fixture(scope="session")
def sample_audio_base64() -> str:
    """Load sample WAV file and convert to base64 string."""
    # For testing, we'll create a minimal WAV file in memory
    # In real implementation, this would load from tests/fixtures/sample_audio.wav
    sample_wav_data = b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
    return base64.b64encode(sample_wav_data).decode('utf-8')


@pytest.fixture(scope="session")
def sample_text() -> dict:
    """Return sample text for TTS/NMT tests in multiple languages."""
    return {
        "english": "Hello, this is a test for the AI services.",
        "hindi": "नमस्ते, यह AI सेवाओं के लिए एक परीक्षण है।",
        "tamil": "வணக்கம், இது AI சேவைகளுக்கான சோதனை.",
        "telugu": "నమస్కారం, ఇది AI సేవల కోసం ఒక పరీక్ష.",
        "kannada": "ನಮಸ್ಕಾರ, ಇದು AI ಸೇವೆಗಳಿಗಾಗಿ ಒಂದು ಪರೀಕ್ಷೆ.",
        "malayalam": "നമസ്കാരം, ഇത് AI സേവനങ്ങൾക്കുള്ള ഒരു പരീക്ഷണമാണ്."
    }


@pytest.fixture(scope="session")
def sample_audio_chunks() -> list:
    """Return sample audio chunks for streaming tests."""
    # Simulate audio chunks for WebSocket streaming tests
    chunk_size = 1024
    num_chunks = 10
    chunks = []
    for i in range(num_chunks):
        chunk_data = b'x' * chunk_size  # Mock audio data
        chunks.append(base64.b64encode(chunk_data).decode('utf-8'))
    return chunks


@pytest.fixture(scope="session")
def sample_text_chunks() -> list:
    """Return sample text chunks for TTS streaming tests."""
    return [
        "Hello, this is the first chunk of text.",
        "This is the second chunk of text.",
        "And this is the final chunk of text."
    ]


# Pytest configuration
pytest_plugins = ["pytest_asyncio"]

# Custom markers
def pytest_configure(config):
    config.addinivalue_line("markers", "integration: Integration tests requiring running services")
    config.addinivalue_line("markers", "unit: Unit tests for isolated components")
    config.addinivalue_line("markers", "e2e: End-to-end tests with browser automation")
    config.addinivalue_line("markers", "slow: Tests that take longer than 5 seconds")
    config.addinivalue_line("markers", "streaming: WebSocket streaming tests")
