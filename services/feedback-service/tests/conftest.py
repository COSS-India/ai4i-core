"""
Shared fixtures for feedback-service integration tests.

All routes are tested against a bare FastAPI app so we never hit a real
database, PII service, or LLM judge.  Auth dependencies are bypassed via
dependency_overrides.
"""

import os
import sys
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Env vars must be set before any app import (pydantic-settings reads them
# at class-definition time for some providers).
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_feedback")
os.environ.setdefault("NMT_DB_URL", "postgresql+asyncpg://test:test@localhost/test_nmt")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("AUTH_SERVICE_URL", "http://localhost:8081")
os.environ.setdefault("JWKS_URL", "http://localhost:8081/.well-known/jwks.json")
os.environ.setdefault("JWT_ISSUER", "test-issuer")
os.environ.setdefault("JWT_AUDIENCE", "test-audience")
os.environ.setdefault("PII_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("LLM_JUDGE_URL", "http://localhost:11434/api/generate")
os.environ.setdefault("LLM_JUDGE_MODEL", "llama3:8b")
os.environ.setdefault("CONFIG_SERVICE_URL", "http://localhost:8082")
os.environ.setdefault("SERVICE_NAME", "feedback-service")

# Ensure the service root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routes.feedback import router as feedback_router, get_db  # noqa: E402
from app.dependencies.auth import AuthRequired, AdminRequired  # noqa: E402


# ---------------------------------------------------------------------------
# Middleware: inject tenant request-state that routes read from request.state
# ---------------------------------------------------------------------------

class _TestStateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = "test_tenant"
        request.state.tenant_schema = "public"
        request.state.email = "test@example.com"
        return await call_next(request)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Async mock DB session with sensible defaults (no existing record)."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    # Default: scalar_one_or_none() returns None (no pre-existing record)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def test_app(mock_db):
    """
    Minimal FastAPI app that includes only the feedback router.
    All external dependencies (DB, auth, PII) are stubbed out.
    """
    app = FastAPI()
    app.add_middleware(_TestStateMiddleware)
    app.include_router(feedback_router)

    # Needed by background-task path (reward <= -0.5)
    app.state.db_session_factory = AsyncMock()

    # Bypass JWT checks
    app.dependency_overrides[AuthRequired] = lambda: None
    app.dependency_overrides[AdminRequired] = lambda: None

    # Bypass real DB session
    async def _override_get_db() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db

    return app


@pytest.fixture
def client(test_app):
    """Synchronous TestClient — backgrounds tasks execute before response returns."""
    with TestClient(test_app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers shared across test modules
# ---------------------------------------------------------------------------

def make_event_payload(**overrides) -> dict:
    """Return a minimal valid implicit-event request body."""
    base = {
        "trace_id":     str(uuid.uuid4()),
        "service_id":   "svc-nmt-v1",
        "task_type":    "nmt",
        "language":     "hi-en",
        "action":       "COPY_TRANSLATION",
        "reward_score": 0.7,
        "source_input": "नमस्ते दुनिया",
        "model_output": "Hello world",
    }
    base.update(overrides)
    return base
