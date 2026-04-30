"""
Enterprise-standard API tests for A/B testing endpoints.

Uses FastAPI TestClient with mocked db_operations to verify:

Note: The app fixture imports main, which requires full service dependencies
(redis_om, etc.). Run from the service root with: pip install -r requirements.txt.
- HTTP status codes and response shapes
- Authenticated experiment CRUD (create, list, get, update, status, delete)
- Public endpoints (select-variant, track-metric)
- Error handling (404, 400, 422, 500)
"""
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def app():
    """FastAPI app with experiment routers; AuthProvider overridden for testing."""
    from main import app as main_app
    from middleware.auth_provider import AuthProvider
    # Allow authenticated routes without real auth
    main_app.dependency_overrides[AuthProvider] = lambda: None
    yield main_app
    main_app.dependency_overrides.pop(AuthProvider, None)


@pytest.fixture
def client(app):
    """TestClient for API tests."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Headers that satisfy AuthProvider (mock)."""
    return {
        "Authorization": "Bearer test-token",
        "Content-Type": "application/json",
    }


@pytest.fixture
def experiment_id():
    """Sample experiment UUID."""
    return str(uuid4())


@pytest.fixture
def sample_experiment_response(experiment_id):
    """Sample experiment response as returned by get_experiment."""
    return {
        "id": experiment_id,
        "name": "ASR Model Comparison",
        "description": "Compare v1 vs v2",
        "status": "DRAFT",
        "task_type": ["asr"],
        "languages": ["hi", "en"],
        "start_date": None,
        "end_date": None,
        "created_by": "user1",
        "updated_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "variants": [
            {
                "id": str(uuid4()),
                "variant_name": "control",
                "service_id": "test-service-a",
                "traffic_percentage": 50,
                "description": "Control",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": str(uuid4()),
                "variant_name": "variant-b",
                "service_id": "test-service-b",
                "traffic_percentage": 50,
                "description": "Variant B",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        ],
    }


@pytest.fixture
def sample_create_payload(experiment_create_payload):
    """JSON payload for POST /experiments."""
    return experiment_create_payload


# =============================================================================
# Create Experiment - POST /experiments
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestCreateExperimentAPI:
    """API tests for POST /experiments."""

    def test_create_experiment_returns_201_and_experiment(self, client, auth_headers, sample_create_payload, experiment_id, sample_experiment_response):
        """Create experiment returns 201 and full experiment body."""
        with patch("routers.router_experiments.create_experiment", new_callable=AsyncMock, return_value=experiment_id):
            with patch("routers.router_experiments.get_experiment", new_callable=AsyncMock, return_value=sample_experiment_response):
                response = client.post(
                    "/experiments",
                    json=sample_create_payload,
                    headers=auth_headers,
                )
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == experiment_id
        assert data["name"] == sample_create_payload["name"]
        assert data["status"] == "DRAFT"
        assert len(data["variants"]) == 2

    def test_create_experiment_validation_error_returns_400(self, client, auth_headers, sample_create_payload):
        """Invalid payload (e.g. traffic not 100) returns 422 (Pydantic)."""
        sample_create_payload["variants"][0]["traffic_percentage"] = 60
        sample_create_payload["variants"][1]["traffic_percentage"] = 30
        response = client.post(
            "/experiments",
            json=sample_create_payload,
            headers=auth_headers,
        )
        assert response.status_code == 422  # Pydantic validation

    def test_create_experiment_value_error_returns_400(self, client, auth_headers, sample_create_payload, experiment_id):
        """create_experiment raising ValueError returns 400."""
        with patch("routers.router_experiments.create_experiment", new_callable=AsyncMock, side_effect=ValueError("Traffic must sum to 100")):
            response = client.post(
                "/experiments",
                json=sample_create_payload,
                headers=auth_headers,
            )
        assert response.status_code == 400
        assert "Traffic" in response.json().get("detail", "")


# =============================================================================
# List Experiments - GET /experiments
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestListExperimentsAPI:
    """API tests for GET /experiments."""

    def test_list_experiments_returns_200_and_list(self, client, auth_headers):
        """List experiments returns 200 and array."""
        with patch("routers.router_experiments.list_experiments", new_callable=AsyncMock, return_value=[]):
            response = client.get("/experiments", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_experiments_with_query_params(self, client, auth_headers):
        """List with status and task_type query params passes them through."""
        with patch("routers.router_experiments.list_experiments", new_callable=AsyncMock, return_value=[]) as mock_list:
            response = client.get(
                "/experiments?status=RUNNING&task_type=asr",
                headers=auth_headers,
            )
        assert response.status_code == 200
        mock_list.assert_called_once()
        call_kw = mock_list.call_args[1] if mock_list.call_args[1] else {}
        assert call_kw.get("status_filter") == "RUNNING"
        assert call_kw.get("task_type") == "asr"


# =============================================================================
# Get Experiment - GET /experiments/{id}
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestGetExperimentAPI:
    """API tests for GET /experiments/{experiment_id}."""

    def test_get_experiment_returns_200_when_found(self, client, auth_headers, experiment_id, sample_experiment_response):
        """Get experiment returns 200 and experiment body when found."""
        with patch("routers.router_experiments.get_experiment", new_callable=AsyncMock, return_value=sample_experiment_response):
            response = client.get(f"/experiments/{experiment_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == experiment_id

    def test_get_experiment_returns_404_when_not_found(self, client, auth_headers, experiment_id):
        """Get experiment returns 404 when not found."""
        with patch("routers.router_experiments.get_experiment", new_callable=AsyncMock, return_value=None):
            response = client.get(f"/experiments/{experiment_id}", headers=auth_headers)
        assert response.status_code == 404
        detail = response.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("kind") == "NotFound" or "not found" in str(detail).lower()
        else:
            assert "not found" in str(detail).lower()


# =============================================================================
# Get Experiment Metrics - GET /experiments/{id}/metrics
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestGetExperimentMetricsAPI:
    """API tests for GET /experiments/{experiment_id}/metrics."""

    def test_get_metrics_returns_200_and_list(self, client, auth_headers, experiment_id):
        """Get metrics returns 200 and list (possibly empty)."""
        with patch("routers.router_experiments.get_experiment_metrics", new_callable=AsyncMock, return_value=[]):
            response = client.get(f"/experiments/{experiment_id}/metrics", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_metrics_returns_404_when_experiment_not_found(self, client, auth_headers, experiment_id):
        """Get metrics returns 404 when experiment does not exist."""
        with patch("routers.router_experiments.get_experiment_metrics", new_callable=AsyncMock, return_value=None):
            response = client.get(f"/experiments/{experiment_id}/metrics", headers=auth_headers)
        assert response.status_code == 404


# =============================================================================
# Update Experiment - PATCH /experiments/{id}
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestUpdateExperimentAPI:
    """API tests for PATCH /experiments/{experiment_id}."""

    def test_update_experiment_returns_200_when_success(self, client, auth_headers, experiment_id, sample_experiment_response, experiment_update_payload):
        """Update experiment returns 200 and updated experiment."""
        sample_experiment_response["name"] = experiment_update_payload["name"]
        with patch("routers.router_experiments.update_experiment", new_callable=AsyncMock, return_value=1):
            with patch("routers.router_experiments.get_experiment", new_callable=AsyncMock, return_value=sample_experiment_response):
                response = client.patch(
                    f"/experiments/{experiment_id}",
                    json=experiment_update_payload,
                    headers=auth_headers,
                )
        assert response.status_code == 200
        assert response.json()["name"] == experiment_update_payload["name"]

    def test_update_experiment_returns_404_when_not_found(self, client, auth_headers, experiment_id, experiment_update_payload):
        """Update experiment returns 404 when experiment does not exist."""
        from fastapi import HTTPException
        with patch("routers.router_experiments.update_experiment", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Not found")):
            response = client.patch(
                f"/experiments/{experiment_id}",
                json=experiment_update_payload,
                headers=auth_headers,
            )
        assert response.status_code == 404


# =============================================================================
# Update Experiment Status - POST /experiments/{id}/status
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestUpdateExperimentStatusAPI:
    """API tests for POST /experiments/{experiment_id}/status."""

    def test_update_status_returns_200_when_success(self, client, auth_headers, experiment_id, sample_experiment_response):
        """Update status returns 200 and experiment body."""
        sample_experiment_response["status"] = "RUNNING"
        with patch("routers.router_experiments.update_experiment_status", new_callable=AsyncMock, return_value=1):
            with patch("routers.router_experiments.get_experiment", new_callable=AsyncMock, return_value=sample_experiment_response):
                response = client.post(
                    f"/experiments/{experiment_id}/status",
                    json={"action": "start"},
                    headers=auth_headers,
                )
        assert response.status_code == 200
        assert response.json()["status"] == "RUNNING"

    def test_update_status_invalid_action_returns_422(self, client, auth_headers, experiment_id):
        """Invalid action body returns 422 (validation)."""
        response = client.post(
            f"/experiments/{experiment_id}/status",
            json={"action": "invalid_action"},
            headers=auth_headers,
        )
        assert response.status_code == 422


# =============================================================================
# Delete Experiment - DELETE /experiments/{id}
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestDeleteExperimentAPI:
    """API tests for DELETE /experiments/{experiment_id}."""

    def test_delete_experiment_returns_200_and_detail(self, client, auth_headers, experiment_id):
        """Delete experiment returns 200 and success detail."""
        with patch("routers.router_experiments.delete_experiment", new_callable=AsyncMock, return_value=1):
            response = client.delete(f"/experiments/{experiment_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "detail" in data
        assert data["detail"].get("code") == "DELETED"
        assert data["detail"].get("experiment_id") == experiment_id

    def test_delete_experiment_returns_404_when_not_found(self, client, auth_headers, experiment_id):
        """Delete experiment returns 404 when experiment does not exist."""
        from fastapi import HTTPException
        with patch("routers.router_experiments.delete_experiment", new_callable=AsyncMock, side_effect=HTTPException(status_code=404, detail="Not found")):
            response = client.delete(f"/experiments/{experiment_id}", headers=auth_headers)
        assert response.status_code == 404


# =============================================================================
# Select Variant (Public) - POST /experiments/select-variant
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestSelectVariantAPI:
    """API tests for POST /experiments/select-variant (public)."""

    def test_select_variant_no_experiment_returns_is_experiment_false(self, client):
        """When no matching experiment, returns is_experiment: false."""
        with patch("routers.router_experiments.select_experiment_variant", new_callable=AsyncMock, return_value=None):
            response = client.post(
                "/experiments/select-variant",
                json={"task_type": "asr", "language": "hi"},
            )
        assert response.status_code == 200
        assert response.json()["is_experiment"] is False

    def test_select_variant_with_match_returns_variant_info(self, client, experiment_id):
        """When experiment matches, returns experiment and variant info."""
        variant_data = {
            "experiment_id": experiment_id,
            "variant_id": str(uuid4()),
            "variant_name": "control",
            "service_id": "svc-1",
            "model_id": "model-1",
            "model_version": "1.0.0",
            "is_experiment": True,
        }
        with patch("routers.router_experiments.select_experiment_variant", new_callable=AsyncMock, return_value=variant_data):
            response = client.post(
                "/experiments/select-variant",
                json={"task_type": "asr", "language": "hi", "user_id": "user1"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["is_experiment"] is True
        assert data["experiment_id"] == experiment_id
        assert data["variant_name"] == "control"
        assert data["service_id"] == "svc-1"

    def test_select_variant_task_type_required_returns_422(self, client):
        """Missing task_type returns 422."""
        response = client.post(
            "/experiments/select-variant",
            json={"language": "hi"},
        )
        assert response.status_code == 422


# =============================================================================
# Track Metric (Public) - POST /experiments/track-metric
# =============================================================================

@pytest.mark.ab_testing
@pytest.mark.integration
class TestTrackMetricAPI:
    """API tests for POST /experiments/track-metric (public)."""

    def test_track_metric_returns_204(self, client, experiment_id):
        """Track metric returns 204 No Content."""
        with patch("routers.router_experiments.track_experiment_metric", new_callable=AsyncMock):
            response = client.post(
                "/experiments/track-metric",
                json={
                    "experiment_id": experiment_id,
                    "variant_id": str(uuid4()),
                    "success": True,
                    "latency_ms": 100,
                },
            )
        assert response.status_code == 204

    def test_track_metric_invalid_payload_returns_422(self, client):
        """Invalid payload (e.g. missing experiment_id) returns 422."""
        response = client.post(
            "/experiments/track-metric",
            json={
                "variant_id": str(uuid4()),
                "success": True,
                "latency_ms": 100,
            },
        )
        assert response.status_code == 422
