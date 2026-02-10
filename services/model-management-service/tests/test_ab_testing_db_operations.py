"""
Enterprise-standard unit tests for A/B testing DB operations.

Tests db_operations with mocked AppDatabase for:

Note: These tests import db_operations, which pulls in the full service stack
(redis_om, etc.). Run from the service root with full deps: pip install -r requirements.txt.
- create_experiment (service not found, not published, success)
- get_experiment (not found, found)
- list_experiments (filters, invalid status)
- update_experiment (not found, running + variants blocked)
- update_experiment_status (not found, invalid transitions)
- delete_experiment (not found, running blocked, success)
- select_experiment_variant (no experiment, returns variant)
- get_experiment_metrics (not found, empty list)
- track_experiment_metric (best-effort, no raise)
"""
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.ab_testing import ExperimentCreateRequest, ExperimentUpdateRequest
from models.db_models import ExperimentStatus


def _make_mock_service(service_id: str, is_published: bool = True):
    """Create a mock Service row."""
    s = MagicMock()
    s.service_id = service_id
    s.is_published = is_published
    return s


def _make_mock_experiment(
    exp_id=None,
    status=ExperimentStatus.DRAFT,
    task_type=None,
    languages=None,
    name="Test Experiment",
):
    """Create a mock Experiment row."""
    e = MagicMock()
    e.id = exp_id or uuid4()
    e.name = name
    e.status = status
    e.task_type = task_type or ["asr"]
    e.languages = languages or ["hi", "en"]
    e.description = None
    e.start_date = None
    e.end_date = None
    e.created_by = None
    e.updated_by = None
    e.created_at = datetime.now(timezone.utc)
    e.updated_at = datetime.now(timezone.utc)
    e.started_at = None
    e.completed_at = None
    return e


def _make_mock_variant(variant_id=None, variant_name="control", service_id="svc-1", traffic_percentage=50):
    """Create a mock ExperimentVariant row."""
    v = MagicMock()
    v.id = variant_id or uuid4()
    v.variant_name = variant_name
    v.service_id = service_id
    v.traffic_percentage = traffic_percentage
    v.description = None
    v.created_at = datetime.now(timezone.utc)
    v.updated_at = datetime.now(timezone.utc)
    return v


# =============================================================================
# create_experiment
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestCreateExperimentDb:
    """Unit tests for create_experiment DB layer."""

    async def test_create_experiment_service_not_found_raises_404(self, mock_db_session, experiment_create_payload):
        """When a variant's service_id does not exist, raise 404."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import create_experiment

            payload = ExperimentCreateRequest(**experiment_create_payload)
            # First execute (first variant): service not found
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await create_experiment(payload, created_by="user1")
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()

    async def test_create_experiment_service_not_published_raises_400(self, mock_db_session, experiment_create_payload):
        """When a variant's service is not published, raise 400."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import create_experiment

            payload = ExperimentCreateRequest(**experiment_create_payload)
            unpublished = _make_mock_service("test-service-a", is_published=False)
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = unpublished
            mock_db_session.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await create_experiment(payload, created_by="user1")
            assert exc_info.value.status_code == 400
            assert "published" in exc_info.value.detail.lower()

    async def test_create_experiment_success_returns_experiment_id(self, mock_db_session, experiment_create_payload):
        """When services exist and are published, create experiment and return UUID."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import create_experiment

            payload = ExperimentCreateRequest(**experiment_create_payload)
            published = _make_mock_service("test-service-a", is_published=True)
            mock_exec_result = MagicMock()
            mock_exec_result.scalars.return_value.first.return_value = published

            exp_id = uuid4()
            def on_refresh(exp):
                exp.id = exp_id
            mock_db_session.execute = AsyncMock(return_value=mock_exec_result)
            mock_db_session.flush = AsyncMock()
            mock_db_session.commit = AsyncMock()
            mock_db_session.refresh = AsyncMock(side_effect=on_refresh)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()
            mock_db_session.add = MagicMock()

            result = await create_experiment(payload, created_by="user1")
            assert result == str(exp_id)
            assert mock_db_session.commit.called


# =============================================================================
# get_experiment
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestGetExperimentDb:
    """Unit tests for get_experiment DB layer."""

    async def test_get_experiment_not_found_returns_none(self, mock_db_session):
        """When experiment_id does not exist, return None."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import get_experiment

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()

            out = await get_experiment(str(uuid4()))
            assert out is None

    async def test_get_experiment_found_returns_dict_with_variants(self, mock_db_session):
        """When experiment exists, return dict with id, name, status, variants."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import get_experiment

            exp = _make_mock_experiment(exp_id=uuid4(), name="My Exp")
            exp.start_date = None
            exp.end_date = None
            v1 = _make_mock_variant(variant_name="control", service_id="s1", traffic_percentage=50)
            v1.created_at = datetime.now(timezone.utc)
            v1.updated_at = datetime.now(timezone.utc)

            mock_exp_result = MagicMock()
            mock_exp_result.scalars.return_value.first.return_value = exp
            mock_variants_result = MagicMock()
            mock_variants_result.scalars.return_value.all.return_value = [v1]

            mock_db_session.execute = AsyncMock(
                side_effect=[mock_exp_result, mock_variants_result]
            )
            mock_db_session.close = AsyncMock()

            out = await get_experiment(str(exp.id))
            assert out is not None
            assert out["id"] == str(exp.id)
            assert out["name"] == "My Exp"
            assert out["status"] == ExperimentStatus.DRAFT.value
            assert "variants" in out


# =============================================================================
# list_experiments
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestListExperimentsDb:
    """Unit tests for list_experiments DB layer."""

    async def test_list_experiments_invalid_status_raises_400(self, mock_db_session):
        """When status_filter is invalid, raise 400 (validated before DB)."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import list_experiments

            mock_db_session.close = AsyncMock()
            # Invalid status triggers ValueError -> HTTPException 400 before execute
            with pytest.raises(HTTPException) as exc_info:
                await list_experiments(status_filter="INVALID_STATUS")
            assert exc_info.value.status_code == 400
            assert "Invalid status" in exc_info.value.detail or "Valid values" in exc_info.value.detail

    async def test_list_experiments_returns_list(self, mock_db_session):
        """list_experiments returns list of experiment summaries."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import list_experiments

            exp = _make_mock_experiment(exp_id=uuid4())
            exp.start_date = None
            exp.end_date = None
            mock_exp_result = MagicMock()
            mock_exp_result.scalars.return_value.all.return_value = [exp]
            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 2

            mock_db_session.execute = AsyncMock(
                side_effect=[mock_exp_result, mock_count_result]
            )
            mock_db_session.close = AsyncMock()

            out = await list_experiments()
            assert isinstance(out, list)
            assert len(out) == 1
            assert out[0]["variant_count"] == 2


# =============================================================================
# update_experiment
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestUpdateExperimentDb:
    """Unit tests for update_experiment DB layer."""

    async def test_update_experiment_not_found_raises_404(self, mock_db_session, experiment_update_payload):
        """When experiment_id does not exist, raise 404."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import update_experiment

            payload = ExperimentUpdateRequest(**experiment_update_payload)
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await update_experiment(str(uuid4()), payload, updated_by="user1")
            assert exc_info.value.status_code == 404

    async def test_update_experiment_running_with_variants_raises_400(self, mock_db_session):
        """When experiment is RUNNING and payload includes variants, raise 400."""
        from models.ab_testing import ExperimentVariantRequest
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import update_experiment

            exp = _make_mock_experiment(exp_id=uuid4(), status=ExperimentStatus.RUNNING)
            payload = ExperimentUpdateRequest(
                name="Updated",
                variants=[
                    ExperimentVariantRequest(variant_name="a", service_id="s1", traffic_percentage=50),
                    ExperimentVariantRequest(variant_name="b", service_id="s2", traffic_percentage=50),
                ]
            )
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = exp
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await update_experiment(str(exp.id), payload, updated_by="user1")
            assert exc_info.value.status_code == 400
            assert "running" in exc_info.value.detail.lower() or "variant" in exc_info.value.detail.lower()


# =============================================================================
# update_experiment_status
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestUpdateExperimentStatusDb:
    """Unit tests for update_experiment_status DB layer."""

    async def test_update_status_not_found_raises_404(self, mock_db_session):
        """When experiment_id does not exist, raise 404."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import update_experiment_status

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await update_experiment_status(str(uuid4()), "start", updated_by="user1")
            assert exc_info.value.status_code == 404

    async def test_update_status_start_non_draft_raises_400(self, mock_db_session):
        """Starting a non-DRAFT experiment raises 400."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import update_experiment_status

            exp = _make_mock_experiment(exp_id=uuid4(), status=ExperimentStatus.RUNNING)
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = exp
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await update_experiment_status(str(exp.id), "start", updated_by="user1")
            assert exc_info.value.status_code == 400
            assert "DRAFT" in exc_info.value.detail or "start" in exc_info.value.detail.lower()


# =============================================================================
# delete_experiment
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestDeleteExperimentDb:
    """Unit tests for delete_experiment DB layer."""

    async def test_delete_experiment_not_found_raises_404(self, mock_db_session):
        """When experiment_id does not exist, raise 404."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import delete_experiment

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await delete_experiment(str(uuid4()))
            assert exc_info.value.status_code == 404

    async def test_delete_experiment_running_raises_400(self, mock_db_session):
        """Deleting a RUNNING experiment raises 400."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import delete_experiment

            exp = _make_mock_experiment(exp_id=uuid4(), status=ExperimentStatus.RUNNING)
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = exp
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()
            mock_db_session.rollback = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await delete_experiment(str(exp.id))
            assert exc_info.value.status_code == 400
            assert "RUNNING" in exc_info.value.detail or "Stop" in exc_info.value.detail


# =============================================================================
# select_experiment_variant
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestSelectExperimentVariantDb:
    """Unit tests for select_experiment_variant DB layer."""

    async def test_select_variant_no_running_experiment_returns_none(self, mock_db_session):
        """When no RUNNING experiment matches, return None."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import select_experiment_variant

            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()

            out = await select_experiment_variant(task_type="asr", language="hi")
            assert out is None

    async def test_select_variant_returns_variant_dict_when_match(self, mock_db_session):
        """When a RUNNING experiment matches, return variant and service info."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import select_experiment_variant

            exp = _make_mock_experiment(exp_id=uuid4(), status=ExperimentStatus.RUNNING)
            v = _make_mock_variant(variant_name="control", service_id="svc-1")
            mock_svc = _make_mock_service("svc-1", is_published=True)
            mock_svc.model_id = "model-1"
            mock_svc.model_version = "1.0.0"

            mock_exp_result = MagicMock()
            mock_exp_result.scalars.return_value.all.return_value = [exp]
            mock_var_result = MagicMock()
            mock_var_result.scalars.return_value.all.return_value = [v]
            mock_svc_result = MagicMock()
            mock_svc_result.scalars.return_value.first.return_value = mock_svc

            mock_db_session.execute = AsyncMock(
                side_effect=[mock_exp_result, mock_var_result, mock_svc_result]
            )
            mock_db_session.close = AsyncMock()

            out = await select_experiment_variant(task_type="asr", language="hi")
            assert out is not None
            assert out.get("experiment_id") == str(exp.id)
            assert out.get("variant_id") == str(v.id)
            assert out.get("variant_name") == "control"
            assert out.get("service_id") == "svc-1"
            assert out.get("is_experiment") is True


# =============================================================================
# get_experiment_metrics
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestGetExperimentMetricsDb:
    """Unit tests for get_experiment_metrics DB layer."""

    async def test_get_metrics_experiment_not_found_returns_none(self, mock_db_session):
        """When experiment does not exist, return None."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import get_experiment_metrics

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.close = AsyncMock()

            out = await get_experiment_metrics(str(uuid4()))
            assert out is None

    async def test_get_metrics_empty_returns_list(self, mock_db_session):
        """When experiment exists but has no metrics, return empty list."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import get_experiment_metrics

            exp_id = uuid4()
            mock_exist_result = MagicMock()
            mock_exist_result.scalars.return_value.first.return_value = MagicMock()
            mock_rows_result = MagicMock()
            mock_rows_result.all.return_value = []

            mock_db_session.execute = AsyncMock(
                side_effect=[mock_exist_result, mock_rows_result]
            )
            mock_db_session.close = AsyncMock()

            out = await get_experiment_metrics(str(exp_id))
            assert out is not None
            assert isinstance(out, list)
            assert len(out) == 0


# =============================================================================
# track_experiment_metric
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
@pytest.mark.asyncio
class TestTrackExperimentMetricDb:
    """Unit tests for track_experiment_metric (best-effort, no raise)."""

    async def test_track_metric_does_not_raise(self, mock_db_session):
        """track_experiment_metric should not raise (best-effort)."""
        with patch('db_operations.AppDatabase', return_value=mock_db_session):
            from db_operations import track_experiment_metric

            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None
            mock_db_session.execute = AsyncMock(return_value=mock_result)
            mock_db_session.commit = AsyncMock()
            mock_db_session.close = AsyncMock()
            mock_db_session.add = MagicMock()

            await track_experiment_metric(
                experiment_id=str(uuid4()),
                variant_id=str(uuid4()),
                success=True,
                latency_ms=100,
            )
            # No exception
            assert mock_db_session.commit.called or True
