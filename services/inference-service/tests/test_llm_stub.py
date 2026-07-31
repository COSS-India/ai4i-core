"""Unit tests for the LLM chat proxy stub (load-test parity with Triton stubs)."""

import pytest

from config import settings
from response_test.stub_dispatcher import get_llm_stub_response


@pytest.fixture
def stub_mode(monkeypatch):
    """Turn stub mode on for the duration of a test."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", True)


def _prompt_of_length(n: int) -> dict:
    return {"model": "stub", "messages": [{"role": "user", "content": "x" * n}]}


def test_returns_none_when_mode_is_off(monkeypatch):
    """With the flag off the chat path must reach the real upstream."""
    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)

    assert get_llm_stub_response(_prompt_of_length(10)) is None


def test_classifies_by_prompt_length(stub_mode):
    """Prompt length picks SMALL / MEDIUM / LARGE buckets (200 / 1000 thresholds)."""
    contents = {
        get_llm_stub_response(_prompt_of_length(n))["choices"][0]["message"]["content"]
        for n in (10, 500, 1500)
    }

    assert len(contents) == 3


def test_body_is_openai_shaped_with_usage(stub_mode):
    """The stub is an OpenAI chat-completion body with a consistent usage block."""
    body = get_llm_stub_response(_prompt_of_length(10))

    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_body_carries_the_fields_the_chat_route_bills_on(stub_mode):
    """set_billed_state reads usage, set_metric_labels reads model.

    Without both present the route would bill zero and label the metric with an
    empty model, silently, so this is the contract that keeps the stub usable
    for a billing-inclusive load test.
    """
    body = get_llm_stub_response(_prompt_of_length(10))

    assert body["usage"]["prompt_tokens"] > 0
    assert body["usage"]["completion_tokens"] > 0
    assert body["model"]


def test_returns_deep_copy(stub_mode):
    """Callers mutating the result must not corrupt the shared stub constants."""
    first = get_llm_stub_response(_prompt_of_length(10))
    first["choices"][0]["message"]["content"] = "mutated"
    second = get_llm_stub_response(_prompt_of_length(10))

    assert second["choices"][0]["message"]["content"] != "mutated"


def test_handles_missing_or_nonstring_messages(stub_mode):
    """Empty / multimodal payloads classify as SMALL instead of raising."""
    assert get_llm_stub_response({}) is not None
    assert get_llm_stub_response(
        {"messages": [{"role": "user", "content": [{"type": "image"}]}]}
    ) is not None


@pytest.mark.asyncio
async def test_proxy_traced_short_circuits_before_mms_and_upstream(stub_mode, monkeypatch):
    """Neither MMS resolution nor the upstream forward may run in stub mode."""
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()

    async def _fail(*args, **kwargs):
        raise AssertionError("stub mode must not reach MMS or the upstream")

    monkeypatch.setattr(service, "resolve_upstream_url", _fail)
    monkeypatch.setattr(service, "forward", _fail)

    status, body = await service.proxy_traced(
        path="/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert status == 200
    assert body["object"] == "chat.completion"


@pytest.mark.asyncio
async def test_proxy_traced_falls_through_when_mode_is_off(monkeypatch):
    """With the flag off the real resolution path must still run."""
    from services.llm_service import OpenAIProxyService

    monkeypatch.setattr(settings, "TRITON_STUB_MODE", False)
    service = OpenAIProxyService()
    called = {}

    async def _resolve(service_id, path):
        called["resolved"] = service_id
        raise LookupError("not found")

    monkeypatch.setattr(service, "resolve_upstream_url", _resolve)

    status, _ = await service.proxy_traced(
        path="/v1/chat/completions", payload=_prompt_of_length(10)
    )

    assert called["resolved"] == "stub"
    assert status == 404
