"""ai4i_core.observability.utils: LLM usage extraction from OpenAI/vLLM bodies."""

import pytest

from ai4i_core.observability import get_llm_cached_tokens, get_llm_usage

_VLLM_RESPONSE = {
    "model": "google/gemma-4-31B-it",
    "usage": {
        "prompt_tokens": 23,
        "total_tokens": 32,
        "completion_tokens": 9,
        "prompt_tokens_details": {"cached_tokens": 0, "created_cache_tokens": 0, "multimodal_tokens": None},
    },
}


def test_usage_counts_are_unchanged():
    assert get_llm_usage(_VLLM_RESPONSE) == (23, 9)


def test_cached_tokens_read_from_prompt_tokens_details():
    body = {"usage": {"prompt_tokens": 1200, "prompt_tokens_details": {"cached_tokens": 1024}}}
    assert get_llm_cached_tokens(body) == 1024


def test_created_cache_tokens_are_not_counted_as_cached():
    body = {"usage": {"prompt_tokens": 40, "prompt_tokens_details": {"cached_tokens": 0, "created_cache_tokens": 32}}}
    assert get_llm_cached_tokens(body) == 0


@pytest.mark.parametrize("chunk", [
    _VLLM_RESPONSE,                                                  # real response, no cache hit
    {"usage": {"prompt_tokens": 5, "prompt_tokens_details": None}},  # flag off: null block
    {"usage": {"prompt_tokens": 5}},                                 # no details block at all
    {"usage": {"prompt_tokens_details": {"cached_tokens": None}}},
    {"usage": {"prompt_tokens_details": {"cached_tokens": "bad"}}},
    {"choices": []},                                                 # streamed delta chunk
    "not-a-dict",
])
def test_absent_or_unusable_cached_tokens_mean_zero(chunk):
    assert get_llm_cached_tokens(chunk) == 0
