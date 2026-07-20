"""Unit tests for the LLM chat proxy stub (load-test parity with Triton stubs)."""

import pytest

from response_test.stub_dispatcher import get_llm_stub_response


def _prompt_of_length(n: int) -> dict:
    return {"model": "stub", "messages": [{"role": "user", "content": "x" * n}]}


def test_classifies_by_prompt_length():
    """Prompt length picks SMALL / MEDIUM / LARGE buckets (200 / 1000 thresholds)."""
    small = get_llm_stub_response(_prompt_of_length(10))
    medium = get_llm_stub_response(_prompt_of_length(500))
    large = get_llm_stub_response(_prompt_of_length(1500))

    # Distinct buckets return distinct completion content.
    contents = {
        small["choices"][0]["message"]["content"],
        medium["choices"][0]["message"]["content"],
        large["choices"][0]["message"]["content"],
    }
    assert len(contents) == 3


def test_body_is_openai_shaped_with_usage():
    """The stub is an OpenAI chat-completion body with a consistent usage block."""
    body = get_llm_stub_response(_prompt_of_length(10))

    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_returns_deep_copy():
    """Callers mutating the result must not corrupt the shared stub constants."""
    first = get_llm_stub_response(_prompt_of_length(10))
    first["choices"][0]["message"]["content"] = "mutated"
    second = get_llm_stub_response(_prompt_of_length(10))
    assert second["choices"][0]["message"]["content"] != "mutated"


def test_handles_missing_or_nonstring_messages():
    """Empty / multimodal payloads classify as SMALL instead of raising."""
    assert get_llm_stub_response({}) is not None
    assert get_llm_stub_response({"messages": [{"role": "user", "content": [{"type": "image"}]}]}) is not None


@pytest.mark.asyncio
async def test_proxy_short_circuits_without_mms_or_upstream(monkeypatch):
    """proxy() returns the stub and never calls proxy_traced() (no MMS/upstream needed)."""
    from services.llm_service import OpenAIProxyService

    service = OpenAIProxyService()

    async def _fail(*args, **kwargs):
        raise AssertionError("proxy_traced() must not be called in stub mode")

    monkeypatch.setattr(service, "proxy_traced", _fail)

    status, body = await service.proxy(path="/v1/chat/completions", payload=_prompt_of_length(10))
    assert status == 200
    assert body["object"] == "chat.completion"
