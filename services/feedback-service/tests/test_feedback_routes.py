"""
Integration tests for feedback-service HTTP routes.

DB, PII service, and LLM judge are all mocked — no external connections
are made.  Auth is bypassed via dependency_overrides in conftest.py.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import make_event_payload


# ---------------------------------------------------------------------------
# Schema validation (no DB call needed)
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Pydantic Literal / Field constraints are enforced before any DB access."""

    def test_invalid_action_returns_422(self, client):
        payload = make_event_payload(action="THUMBS_DOWN")
        resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 422

    def test_invalid_task_type_returns_422(self, client):
        payload = make_event_payload(task_type="video")
        resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 422

    def test_reward_score_above_range_returns_422(self, client):
        payload = make_event_payload(reward_score=1.5)
        resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 422

    def test_reward_score_below_range_returns_422(self, client):
        payload = make_event_payload(reward_score=-1.5)
        resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 422

    def test_correction_action_accepted(self, client):
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp, \
             patch("app.routes.feedback._bg_evaluate"):
            mp.return_value = ("src", "out")
            payload = make_event_payload(action="CORRECTION", reward_score=-0.6)
            resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 200

    def test_abandon_action_accepted(self, client):
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp, \
             patch("app.routes.feedback._bg_evaluate"):
            mp.return_value = ("src", "out")
            payload = make_event_payload(action="ABANDON", reward_score=-1.0)
            resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /event — new record creation
# ---------------------------------------------------------------------------

class TestImplicitEvent:
    """Tests for the /event ingestion endpoint."""

    def test_missing_source_input_for_new_trace_returns_422(self, client):
        """source_input + model_output are required when the trace_id is new."""
        payload = {
            "trace_id":     str(uuid.uuid4()),
            "service_id":   "svc-1",
            "task_type":    "nmt",
            "action":       "COPY_TRANSLATION",
            "reward_score": 0.7,
            # source_input and model_output intentionally omitted
        }
        resp = client.post("/api/v1/feedback/event", json=payload)
        assert resp.status_code == 422

    def test_high_reward_marks_status_pass(self, client):
        """reward_score >= 0.5 auto-sets ai_status to PASS without LLM evaluation."""
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp:
            mp.return_value = ("नमस्ते दुनिया", "Hello world")
            payload = make_event_payload(action="COPY_TRANSLATION", reward_score=0.7)
            resp = client.post("/api/v1/feedback/event", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_status"] == "PASS"
        assert data["trace_id"] == payload["trace_id"]

    def test_low_reward_keeps_status_pending_and_queues_evaluation(self, client):
        """reward_score <= -0.5 triggers background LLM evaluation; status stays PENDING."""
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp, \
             patch("app.routes.feedback._bg_evaluate") as mock_bg:
            mp.return_value = ("src", "out")
            payload = make_event_payload(action="RETRANSLATE", reward_score=-0.5)
            resp = client.post("/api/v1/feedback/event", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_status"] == "PENDING"
        # Background task must have been scheduled
        mock_bg.assert_called_once()

    def test_abandon_queues_evaluation(self, client):
        """ABANDON (reward -1.0) also triggers the evaluation background task."""
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp, \
             patch("app.routes.feedback._bg_evaluate") as mock_bg:
            mp.return_value = ("src", "out")
            payload = make_event_payload(action="ABANDON", reward_score=-1.0)
            resp = client.post("/api/v1/feedback/event", json=payload)

        assert resp.status_code == 200
        mock_bg.assert_called_once()

    def test_event_accumulates_event_log_on_existing_record(self, client, mock_db):
        """A second event for the same trace_id appends to event_log."""
        existing = MagicMock()
        existing.trace_id = "tr-log-test"
        existing.implicit_score = 70
        existing.event_log = [{"action": "COPY_TRANSLATION", "reward_score": 0.7, "metrics": {}}]
        existing.ai_status = "PASS"
        existing.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        payload = make_event_payload(
            trace_id="tr-log-test",
            action="CLEAR_RESULTS",
            reward_score=-0.3,
            # source_input / model_output not needed for an existing record
        )
        del payload["source_input"]
        del payload["model_output"]

        resp = client.post("/api/v1/feedback/event", json=payload)

        assert resp.status_code == 200
        # event_log was mutated in-place by the route
        assert len(existing.event_log) == 2
        assert existing.event_log[1]["action"] == "CLEAR_RESULTS"
        assert existing.event_log[1]["reward_score"] == -0.3

    def test_implicit_score_accumulates(self, client, mock_db):
        """implicit_score is updated by int(reward_score * 100) per event."""
        existing = MagicMock()
        existing.trace_id = "tr-score-test"
        existing.implicit_score = 70   # 0.7 * 100 from a previous COPY_TRANSLATION
        existing.event_log = []
        existing.ai_status = "PASS"
        existing.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        payload = make_event_payload(
            trace_id="tr-score-test",
            action="CLEAR_RESULTS",
            reward_score=-0.3,
        )
        del payload["source_input"]
        del payload["model_output"]

        client.post("/api/v1/feedback/event", json=payload)

        # 70 + int(-0.3 * 100) = 70 + (-30) = 40
        assert existing.implicit_score == 40


# ---------------------------------------------------------------------------
# GET /status/{trace_id}
# ---------------------------------------------------------------------------

class TestStatusEndpoint:

    def test_unknown_trace_returns_404(self, client, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/v1/feedback/status/nonexistent-trace-id")
        assert resp.status_code == 404

    def test_known_trace_returns_record(self, client, mock_db):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.trace_id = "tr-known"
        existing.organization = "example.com"
        existing.tenant_id = "test_tenant"
        existing.service_id = "svc-1"
        existing.task_type = "nmt"
        existing.language = "hi-en"
        existing.source_input = "hello"
        existing.model_output = "नमस्ते"
        existing.human_correction = None
        existing.feedback_source = "system"
        existing.rating = None
        existing.implicit_score = 70
        existing.event_log = []
        existing.ai_status = "PASS"
        existing.error_type = None
        existing.severity = None
        existing.payload = {}
        existing.created_at = None
        existing.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/v1/feedback/status/tr-known")
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == "tr-known"
        assert resp.json()["ai_status"] == "PASS"


# ---------------------------------------------------------------------------
# POST / — explicit feedback
# ---------------------------------------------------------------------------

class TestExplicitFeedback:

    def test_duplicate_trace_returns_409(self, client, mock_db):
        """Submitting explicit feedback for a trace_id that already exists → 409."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # record exists
        mock_db.execute.return_value = mock_result

        payload = {
            "trace_id":     "tr-dup",
            "service_id":   "svc-1",
            "task_type":    "nmt",
            "source_input": "hello",
            "model_output": "नमस्ते",
        }
        resp = client.post("/api/v1/feedback", json=payload)
        assert resp.status_code == 409

    def test_new_explicit_feedback_accepted(self, client):
        """Valid explicit feedback for a new trace_id returns 200."""
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp:
            mp.return_value = ("hello", "नमस्ते")
            payload = {
                "trace_id":     str(uuid.uuid4()),
                "service_id":   "svc-1",
                "task_type":    "nmt",
                "source_input": "hello",
                "model_output": "नमस्ते",
            }
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_status"] == "PENDING"
        assert "Feedback recorded" in data["message"]

    def test_explicit_feedback_with_trigger_evaluation(self, client):
        """trigger_evaluation=true schedules background LLM eval."""
        with patch("app.routes.feedback.redact_pair", new_callable=AsyncMock) as mp, \
             patch("app.routes.feedback._bg_evaluate") as mock_bg:
            mp.return_value = ("hello", "नमस्ते")
            payload = {
                "trace_id":          str(uuid.uuid4()),
                "service_id":        "svc-1",
                "task_type":         "nmt",
                "source_input":      "hello",
                "model_output":      "नमस्ते",
                "trigger_evaluation": True,
            }
            resp = client.post("/api/v1/feedback", json=payload)

        assert resp.status_code == 200
        mock_bg.assert_called_once()
        assert "Evaluation queued" in resp.json()["message"]
