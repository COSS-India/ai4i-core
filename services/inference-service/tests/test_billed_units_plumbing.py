"""Unit tests: Orchestrator.route_inference mirrors the task_service's
already-computed billed unit counts onto request.state (AI4IDS-2532).

This is the plumbing ObservabilityMiddleware relies on instead of
re-deriving its own counts from the raw request/response body.
"""
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, ".")

from orchestrator.orchestrator import Orchestrator


def _make_orchestrator() -> Orchestrator:
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _make_task_service(billed_input=0, source_lang="", target_lang=""):
    task_service = MagicMock()
    task_service.billed_input = billed_input
    task_service.source_lang = source_lang
    task_service.target_lang = target_lang
    response = MagicMock()
    response.dict.return_value = {"ok": True}
    task_service.process = AsyncMock(return_value=response)
    return task_service


@pytest.mark.asyncio
async def test_billed_state_mirrored_onto_request_state():
    orch = _make_orchestrator()
    task_service = _make_task_service(
        billed_input=42, source_lang="en", target_lang="hi",
    )

    fake_request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/nmt/inference"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )

    with patch.object(orch, "_validate_task_type"), \
         patch.object(orch, "_resolve_service_and_model", new=AsyncMock(return_value={"tier_ids": []})), \
         patch.object(orch, "_get_task_service", return_value=task_service):
        result = await orch.route_inference(
            payload={"task_type": "NMT"}, request=fake_request,
        )

    assert fake_request.state.billed_input == 42
    # non-LLM is input-only — the orchestrator never passes a computed output,
    # so billed_output stays the helper's default 0 (middleware ignores it for
    # non-LLM anyway; only the LLM route passes a real output count).
    assert fake_request.state.billed_output == 0
    # language labels (metric labels, not billing) also mirrored
    assert fake_request.state.source_lang == "en"
    assert fake_request.state.target_lang == "hi"
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_missing_billed_attrs_default_to_zero_unknown():
    """A task_service that never set billed_* (e.g. an older/unmigrated
    subclass) must not crash route_inference — getattr defaults apply."""
    orch = _make_orchestrator()
    task_service = MagicMock(spec=["process"])
    response = MagicMock()
    response.dict.return_value = {"ok": True}
    task_service.process = AsyncMock(return_value=response)

    fake_request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/nmt/inference"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )

    with patch.object(orch, "_validate_task_type"), \
         patch.object(orch, "_resolve_service_and_model", new=AsyncMock(return_value={"tier_ids": []})), \
         patch.object(orch, "_get_task_service", return_value=task_service):
        await orch.route_inference(payload={"task_type": "NMT"}, request=fake_request)

    assert fake_request.state.billed_input == 0
    assert fake_request.state.source_lang == ""
    assert fake_request.state.target_lang == ""


@pytest.mark.asyncio
async def test_service_id_mirrored_onto_request_state():
    """service_id (including any SMR-fallback-resolved value, carried in
    service_info["serviceId"]) must reach request.state so
    ObservabilityMiddleware never needs to re-parse the body for it."""
    orch = _make_orchestrator()
    task_service = _make_task_service(billed_input=1)

    fake_request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/nmt/inference"),
        method="POST",
        headers={},
        state=SimpleNamespace(),
    )

    with patch.object(orch, "_validate_task_type"), \
         patch.object(orch, "_resolve_service_and_model",
                      new=AsyncMock(return_value={"tier_ids": [], "serviceId": "resolved-svc-1"})), \
         patch.object(orch, "_get_task_service", return_value=task_service):
        await orch.route_inference(payload={"task_type": "NMT"}, request=fake_request)

    assert fake_request.state.service_id == "resolved-svc-1"


@pytest.mark.asyncio
async def test_no_request_object_skips_state_mirroring_without_error():
    """Internal callers that don't pass a Request (no HTTP context) must not
    crash trying to set request.state on None."""
    orch = _make_orchestrator()
    task_service = _make_task_service(billed_input=5)

    with patch.object(orch, "_validate_task_type"), \
         patch.object(orch, "_resolve_service_and_model", new=AsyncMock(return_value={"tier_ids": []})), \
         patch.object(orch, "_get_task_service", return_value=task_service):
        result = await orch.route_inference(payload={"task_type": "NMT"}, request=None)

    assert result == {"ok": True}
