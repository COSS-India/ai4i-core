"""
Integration tests for admin-only routes:
  POST /api/v1/feedback/human_correction
  POST /api/v1/feedback/override_pass
  GET  /api/v1/feedback/latest
  POST /api/v1/feedback/batch_process

DB, NMT DB, and LLM judge are all mocked — no external connections made.
Auth is bypassed via dependency_overrides.
"""

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.dependencies.auth import AdminRequired
from app.routes.correction import router as correction_router
from app.routes.correction import get_db as correction_get_db
from app.routes.evaluation import router as evaluation_router
from app.routes.evaluation import get_db as evaluation_get_db
from app.routes.feedback import router as feedback_router
from app.routes.feedback import get_db as feedback_get_db


# ---------------------------------------------------------------------------
# Middleware — inject tenant state
# ---------------------------------------------------------------------------

class _TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = "test_tenant"
        request.state.tenant_schema = "public"
        request.state.email = "admin@example.com"
        return await call_next(request)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_mock_db():
    """Mock DB session that handles both scalar and list query patterns."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_result.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


@pytest.fixture
def admin_app(admin_mock_db):
    app = FastAPI()
    app.add_middleware(_TenantMiddleware)
    app.include_router(feedback_router)
    app.include_router(correction_router)
    app.include_router(evaluation_router)
    app.state.db_session_factory = AsyncMock()

    app.dependency_overrides[AdminRequired] = lambda: None

    async def _override_get_db() -> AsyncGenerator:
        yield admin_mock_db

    app.dependency_overrides[feedback_get_db] = _override_get_db
    app.dependency_overrides[correction_get_db] = _override_get_db
    app.dependency_overrides[evaluation_get_db] = _override_get_db

    return app


@pytest.fixture
def admin_client(admin_app):
    with TestClient(admin_app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /human_correction
# ---------------------------------------------------------------------------

class TestHumanCorrection:

    def test_unknown_trace_returns_404(self, admin_client):
        resp = admin_client.post(
            "/api/v1/feedback/human_correction",
            json={"trace_id": "nonexistent", "corrected_output": "Fixed text"},
        )
        assert resp.status_code == 404

    def test_known_trace_saves_correction(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-correction"
        existing.ai_status = "FAIL"
        existing.source_input = "hello"
        existing.model_output = "hola"
        existing.payload = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        resp = admin_client.post(
            "/api/v1/feedback/human_correction",
            json={"trace_id": "tr-correction", "corrected_output": "Hello (corrected)"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "tr-correction"
        assert "Human correction saved" in data["message"]

    def test_correction_creates_golden_pair(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-golden"
        existing.ai_status = "FAIL"
        existing.source_input = "source text"
        existing.model_output = "bad translation"
        existing.payload = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        admin_client.post(
            "/api/v1/feedback/human_correction",
            json={"trace_id": "tr-golden", "corrected_output": "good translation"},
        )

        # Verify golden_pair was written to payload
        assert existing.payload["golden_pair"]["source"] == "source text"
        assert existing.payload["golden_pair"]["rejected"] == "bad translation"
        assert existing.payload["golden_pair"]["chosen"] == "good translation"
        assert existing.human_correction == "good translation"


# ---------------------------------------------------------------------------
# POST /override_pass
# ---------------------------------------------------------------------------

class TestOverridePass:

    def test_unknown_trace_returns_404(self, admin_client):
        resp = admin_client.post(
            "/api/v1/feedback/override_pass",
            json={"trace_id": "no-such-trace"},
        )
        assert resp.status_code == 404

    def test_non_fail_status_returns_400(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-pending"
        existing.ai_status = "PENDING"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        resp = admin_client.post(
            "/api/v1/feedback/override_pass",
            json={"trace_id": "tr-pending"},
        )
        assert resp.status_code == 400
        assert "PENDING" in resp.json()["detail"]

    def test_fail_record_overridden_to_pass(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-fail"
        existing.ai_status = "FAIL"
        existing.payload = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        resp = admin_client.post(
            "/api/v1/feedback/override_pass",
            json={"trace_id": "tr-fail"},
        )

        assert resp.status_code == 200
        assert existing.ai_status == "PASS"
        assert resp.json()["ai_status"] == "PASS"

    def test_override_stores_reason(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-reason"
        existing.ai_status = "FAIL"
        existing.payload = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        admin_client.post(
            "/api/v1/feedback/override_pass",
            json={"trace_id": "tr-reason", "reason": "False positive — context understood"},
        )

        assert existing.payload["override_reason"] == "False positive — context understood"

    def test_override_without_reason_uses_default(self, admin_client, admin_mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-no-reason"
        existing.ai_status = "FAIL"
        existing.payload = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        admin_mock_db.execute.return_value = mock_result

        admin_client.post(
            "/api/v1/feedback/override_pass",
            json={"trace_id": "tr-no-reason"},
        )

        assert "Manual override" in existing.payload["override_reason"]


# ---------------------------------------------------------------------------
# GET /latest
# ---------------------------------------------------------------------------

class TestLatestRecords:

    def test_returns_empty_list_when_no_records(self, admin_client):
        resp = admin_client.get("/api/v1/feedback/latest")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_records(self, admin_client, admin_mock_db):
        record = MagicMock()
        record.id = uuid.uuid4()
        record.trace_id = "tr-latest"
        record.organization = "example.com"
        record.tenant_id = "test_tenant"
        record.service_id = "svc-nmt"
        record.task_type = "nmt"
        record.language = "hi-en"
        record.source_input = "hello"
        record.model_output = "namaste"
        record.human_correction = None
        record.feedback_source = "system"
        record.rating = None
        record.implicit_score = 70
        record.event_log = []
        record.ai_status = "PASS"
        record.error_type = None
        record.severity = None
        record.payload = {}
        record.created_at = None
        record.updated_at = None

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [record]
        mock_result.scalars.return_value = mock_scalars
        admin_mock_db.execute.return_value = mock_result

        resp = admin_client.get("/api/v1/feedback/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["trace_id"] == "tr-latest"
        assert data[0]["ai_status"] == "PASS"

    def test_limit_capped_at_1000(self, admin_client):
        # Requesting limit=9999 should not error — the route caps at 1000 internally.
        resp = admin_client.get("/api/v1/feedback/latest?limit=9999")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /batch_process
# ---------------------------------------------------------------------------

class TestBatchProcess:

    def test_empty_nmt_db_returns_zero_queued(self, admin_client):
        with patch("app.services.nmt_reader.fetch_nmt_records", new_callable=AsyncMock) as mock_nmt:
            mock_nmt.return_value = []
            resp = admin_client.post(
                "/api/v1/feedback/batch_process",
                json={"limit": 10, "offset": 0},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["queued"] == 0
        assert data["skipped"] == 0

    def test_nmt_db_error_returns_503(self, admin_client):
        with patch("app.services.nmt_reader.fetch_nmt_records", new_callable=AsyncMock) as mock_nmt:
            mock_nmt.side_effect = RuntimeError("NMT_DB_URL is not set.")
            resp = admin_client.post(
                "/api/v1/feedback/batch_process",
                json={"limit": 10},
            )

        assert resp.status_code == 503
        assert "NMT_DB_URL" in resp.json()["detail"]

    def test_new_nmt_records_are_queued(self, admin_client, admin_mock_db):
        nmt_rows = [
            {
                "trace_id": str(uuid.uuid4()),
                "source_text": "hello",
                "translated_text": "namaste",
                "source_language": "en",
                "target_language": "hi",
                "model_id": "nmt-v1",
                "created_at": None,
            }
        ]
        with patch("app.services.nmt_reader.fetch_nmt_records", new_callable=AsyncMock) as mock_nmt, \
             patch("app.routes.evaluation._bg_batch_evaluate") as mock_bg:
            mock_nmt.return_value = nmt_rows
            resp = admin_client.post(
                "/api/v1/feedback/batch_process",
                json={"limit": 10, "skip_evaluated": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["queued"] == 1
        assert data["skipped"] == 0
        mock_bg.assert_called_once()

    def test_already_evaluated_records_are_skipped(self, admin_client, admin_mock_db):
        trace_id = str(uuid.uuid4())
        nmt_rows = [
            {
                "trace_id": trace_id,
                "source_text": "hello",
                "translated_text": "namaste",
                "source_language": "en",
                "target_language": "hi",
                "model_id": "nmt-v1",
                "created_at": None,
            }
        ]

        # Simulate this trace_id already being in feedback_metrics
        mock_result = MagicMock()
        mock_result.all.return_value = [(trace_id,)]
        mock_result.scalar_one_or_none.return_value = None
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        admin_mock_db.execute.return_value = mock_result

        with patch("app.services.nmt_reader.fetch_nmt_records", new_callable=AsyncMock) as mock_nmt:
            mock_nmt.return_value = nmt_rows
            resp = admin_client.post(
                "/api/v1/feedback/batch_process",
                json={"limit": 10, "skip_evaluated": True},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["queued"] == 0
        assert data["skipped"] == 1

    def test_validation_rejects_limit_above_500(self, admin_client):
        resp = admin_client.post(
            "/api/v1/feedback/batch_process",
            json={"limit": 501},
        )
        assert resp.status_code == 422
