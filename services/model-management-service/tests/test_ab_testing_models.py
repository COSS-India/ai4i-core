"""
Enterprise-standard unit tests for A/B testing Pydantic models.

Covers validation rules for:
- ExperimentCreateRequest, ExperimentUpdateRequest
- ExperimentVariantRequest, ExperimentStatusUpdateRequest
- ExperimentVariantSelectionRequest, ExperimentMetricTrackRequest
"""
import os
import sys
from datetime import datetime, timedelta

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.ab_testing import (
    ExperimentCreateRequest,
    ExperimentUpdateRequest,
    ExperimentVariantRequest,
    ExperimentStatusUpdateRequest,
    ExperimentVariantSelectionRequest,
    ExperimentMetricTrackRequest,
)


# =============================================================================
# ExperimentVariantRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentVariantRequest:
    """Unit tests for ExperimentVariantRequest validation."""

    def test_valid_variant_request_accepts_all_fields(self):
        """Valid variant with all fields should parse successfully."""
        data = {
            "variant_name": "control",
            "service_id": "svc-1",
            "traffic_percentage": 50,
            "description": "Control variant"
        }
        req = ExperimentVariantRequest(**data)
        assert req.variant_name == "control"
        assert req.service_id == "svc-1"
        assert req.traffic_percentage == 50
        assert req.description == "Control variant"

    def test_variant_name_stripped_of_whitespace(self):
        """Variant name should be stripped of leading/trailing whitespace."""
        req = ExperimentVariantRequest(
            variant_name="  control  ",
            service_id="svc-1",
            traffic_percentage=50
        )
        assert req.variant_name == "control"

    def test_variant_name_empty_raises(self):
        """Empty variant name should raise ValueError."""
        with pytest.raises(ValueError, match="Variant name cannot be empty"):
            ExperimentVariantRequest(
                variant_name="",
                service_id="svc-1",
                traffic_percentage=50
            )

    def test_variant_name_whitespace_only_raises(self):
        """Whitespace-only variant name should raise ValueError."""
        with pytest.raises(ValueError, match="Variant name cannot be empty"):
            ExperimentVariantRequest(
                variant_name="   ",
                service_id="svc-1",
                traffic_percentage=50
            )

    def test_traffic_percentage_bounds_0_and_100(self):
        """Traffic percentage must be between 0 and 100 inclusive."""
        ExperimentVariantRequest(
            variant_name="a", service_id="s", traffic_percentage=0
        )
        ExperimentVariantRequest(
            variant_name="b", service_id="s", traffic_percentage=100
        )
        with pytest.raises(ValueError):
            ExperimentVariantRequest(
                variant_name="c", service_id="s", traffic_percentage=-1
            )
        with pytest.raises(ValueError):
            ExperimentVariantRequest(
                variant_name="d", service_id="s", traffic_percentage=101
            )


# =============================================================================
# ExperimentCreateRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentCreateRequest:
    """Unit tests for ExperimentCreateRequest validation."""

    def test_valid_create_request_minimal(self, experiment_create_payload):
        """Valid create request with minimal required fields should parse."""
        req = ExperimentCreateRequest(**experiment_create_payload)
        assert req.name == "ASR Model Comparison"
        assert len(req.variants) == 2
        assert sum(v.traffic_percentage for v in req.variants) == 100

    def test_valid_create_request_with_dates(self, experiment_create_payload):
        """Valid create request with start_date and end_date."""
        start = datetime.utcnow()
        end = start + timedelta(days=30)
        experiment_create_payload["start_date"] = start.isoformat()
        experiment_create_payload["end_date"] = end.isoformat()
        req = ExperimentCreateRequest(**experiment_create_payload)
        assert req.start_date is not None
        assert req.end_date is not None

    def test_name_empty_raises(self, experiment_create_payload):
        """Empty experiment name should raise (ValueError or Pydantic ValidationError)."""
        experiment_create_payload["name"] = ""
        with pytest.raises((ValueError, Exception)) as exc_info:
            ExperimentCreateRequest(**experiment_create_payload)
        msg = str(exc_info.value).lower()
        assert "empty" in msg or "at least 1 character" in msg or "string_too_short" in msg

    def test_name_whitespace_only_raises(self, experiment_create_payload):
        """Whitespace-only name should raise ValueError."""
        experiment_create_payload["name"] = "   "
        with pytest.raises(ValueError, match="Experiment name cannot be empty"):
            ExperimentCreateRequest(**experiment_create_payload)

    def test_fewer_than_two_variants_raises(self, experiment_create_payload):
        """Fewer than 2 variants should raise (ValueError or Pydantic ValidationError)."""
        experiment_create_payload["variants"] = [
            {"variant_name": "only", "service_id": "s1", "traffic_percentage": 100}
        ]
        with pytest.raises((ValueError, Exception)) as exc_info:
            ExperimentCreateRequest(**experiment_create_payload)
        msg = str(exc_info.value).lower()
        assert "at least 2" in msg or "too_short" in msg or "variants" in msg

    def test_traffic_percentages_must_sum_to_100(self, experiment_create_payload):
        """Traffic percentages that do not sum to 100 should raise ValueError."""
        experiment_create_payload["variants"] = [
            {"variant_name": "a", "service_id": "s1", "traffic_percentage": 50},
            {"variant_name": "b", "service_id": "s2", "traffic_percentage": 40},
        ]
        with pytest.raises(ValueError, match="Traffic percentages must sum to 100"):
            ExperimentCreateRequest(**experiment_create_payload)

    def test_duplicate_variant_names_raise(self, experiment_create_payload):
        """Duplicate variant names should raise ValueError."""
        experiment_create_payload["variants"] = [
            {"variant_name": "same", "service_id": "s1", "traffic_percentage": 50},
            {"variant_name": "same", "service_id": "s2", "traffic_percentage": 50},
        ]
        with pytest.raises(ValueError, match="Variant names must be unique"):
            ExperimentCreateRequest(**experiment_create_payload)

    def test_invalid_task_type_raises(self, experiment_create_payload):
        """Invalid task_type value should raise ValueError."""
        experiment_create_payload["task_type"] = ["invalid_task"]
        with pytest.raises(ValueError, match="Invalid task type"):
            ExperimentCreateRequest(**experiment_create_payload)

    def test_valid_task_types_accepted(self, experiment_create_payload):
        """Valid task types (asr, nmt, tts, ocr, etc.) should be accepted."""
        for task in ["asr", "nmt", "tts", "ocr"]:
            experiment_create_payload["task_type"] = [task]
            req = ExperimentCreateRequest(**experiment_create_payload)
            assert req.task_type == [task]

    def test_end_date_before_start_date_raises(self, experiment_create_payload):
        """End date before start date should raise ValueError."""
        start = datetime.utcnow()
        end = start - timedelta(days=1)
        experiment_create_payload["start_date"] = start.isoformat()
        experiment_create_payload["end_date"] = end.isoformat()
        with pytest.raises(ValueError, match="End date must be after start date"):
            ExperimentCreateRequest(**experiment_create_payload)


# =============================================================================
# ExperimentUpdateRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentUpdateRequest:
    """Unit tests for ExperimentUpdateRequest validation."""

    def test_update_request_all_optional(self):
        """All fields in update request are optional."""
        req = ExperimentUpdateRequest()
        assert req.name is None
        assert req.variants is None

    def test_update_variants_must_sum_to_100_if_provided(self):
        """If variants are provided in update, they must sum to 100."""
        with pytest.raises(ValueError, match="Traffic percentages must sum to 100"):
            ExperimentUpdateRequest(
                variants=[
                    ExperimentVariantRequest(
                        variant_name="a", service_id="s1", traffic_percentage=60
                    ),
                    ExperimentVariantRequest(
                        variant_name="b", service_id="s2", traffic_percentage=30
                    ),
                ]
            )

    def test_update_variants_duplicate_names_raise(self):
        """Update with duplicate variant names should raise."""
        with pytest.raises(ValueError, match="Variant names must be unique"):
            ExperimentUpdateRequest(
                variants=[
                    ExperimentVariantRequest(
                        variant_name="dup", service_id="s1", traffic_percentage=50
                    ),
                    ExperimentVariantRequest(
                        variant_name="dup", service_id="s2", traffic_percentage=50
                    ),
                ]
            )


# =============================================================================
# ExperimentStatusUpdateRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentStatusUpdateRequest:
    """Unit tests for ExperimentStatusUpdateRequest validation."""

    @pytest.mark.parametrize("action", ["start", "stop", "pause", "resume", "cancel"])
    def test_valid_actions_accepted(self, action):
        """All valid actions should be accepted and lowercased."""
        req = ExperimentStatusUpdateRequest(action=action)
        assert req.action == action

    def test_action_case_insensitive(self):
        """Action should be normalized to lowercase."""
        req = ExperimentStatusUpdateRequest(action="START")
        assert req.action == "start"

    def test_invalid_action_raises(self):
        """Invalid action should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid action"):
            ExperimentStatusUpdateRequest(action="invalid")


# =============================================================================
# ExperimentVariantSelectionRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentVariantSelectionRequest:
    """Unit tests for ExperimentVariantSelectionRequest."""

    def test_task_type_required(self):
        """task_type is required."""
        req = ExperimentVariantSelectionRequest(task_type="asr")
        assert req.task_type == "asr"

    def test_optional_fields_default_none(self):
        """language, request_id, user_id, service_id are optional."""
        req = ExperimentVariantSelectionRequest(task_type="nmt")
        assert req.language is None
        assert req.request_id is None
        assert req.user_id is None
        assert req.service_id is None

    def test_all_fields_accepted(self):
        """All fields can be set."""
        req = ExperimentVariantSelectionRequest(
            task_type="asr",
            language="hi",
            request_id="req-1",
            user_id="user-1",
            service_id="svc-1"
        )
        assert req.task_type == "asr"
        assert req.language == "hi"
        assert req.request_id == "req-1"
        assert req.user_id == "user-1"
        assert req.service_id == "svc-1"


# =============================================================================
# ExperimentMetricTrackRequest
# =============================================================================

@pytest.mark.unit
@pytest.mark.ab_testing
class TestExperimentMetricTrackRequest:
    """Unit tests for ExperimentMetricTrackRequest."""

    def test_required_fields(self):
        """experiment_id, variant_id, success, latency_ms are required."""
        req = ExperimentMetricTrackRequest(
            experiment_id="exp-uuid",
            variant_id="var-uuid",
            success=True,
            latency_ms=100
        )
        assert req.experiment_id == "exp-uuid"
        assert req.variant_id == "var-uuid"
        assert req.success is True
        assert req.latency_ms == 100

    def test_latency_non_negative(self):
        """latency_ms must be >= 0."""
        ExperimentMetricTrackRequest(
            experiment_id="e", variant_id="v", success=True, latency_ms=0
        )
        with pytest.raises(ValueError):
            ExperimentMetricTrackRequest(
                experiment_id="e", variant_id="v", success=True, latency_ms=-1
            )

    def test_custom_metrics_optional(self):
        """custom_metrics is optional and defaults to empty dict."""
        req = ExperimentMetricTrackRequest(
            experiment_id="e", variant_id="v", success=True, latency_ms=50
        )
        assert req.custom_metrics is not None
        assert req.custom_metrics == {}
