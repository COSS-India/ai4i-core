"""Stub responses for the LLM chat proxy.

Unlike the other modules in this package, these are NOT Triton KServe v2 shapes.
The LLM path (OpenAIProxyService.proxy) returns the upstream body verbatim, so
the stubs mirror an OpenAI-compatible chat-completion object: the route forwards
it unchanged and proxy_traced reads `usage` for the ai-inference token spans.

Three sizes based on the request prompt's character length:
  SMALL_LLM_RESPONSE   — short reply    (< 200 chars prompt)
  MEDIUM_LLM_RESPONSE  — a few sentences (200–999 chars prompt)
  LARGE_LLM_RESPONSE   — full paragraph  (>= 1000 chars prompt)
"""

from typing import Any


def _completion(content: str, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    """Build an OpenAI chat-completion body with a consistent usage block."""
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "stub",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


SMALL_LLM_RESPONSE: dict[str, Any] = _completion(
    "Hello! How can I help you today?",
    prompt_tokens=8,
    completion_tokens=9,
)

MEDIUM_LLM_RESPONSE: dict[str, Any] = _completion(
    "Sure, here is a concise summary. The meeting is scheduled for Monday at "
    "10 AM. Please make sure all required documents are ready before the "
    "session, and confirm your attendance by replying to this message.",
    prompt_tokens=120,
    completion_tokens=44,
)

LARGE_LLM_RESPONSE: dict[str, Any] = _completion(
    "Here is a detailed response. " + (
        "The proposed approach balances throughput and latency by batching "
        "requests where possible while keeping per-request overhead low. "
        "Each stage of the pipeline is instrumented so the time spent in "
        "validation, preprocessing, inference, and post-processing can be "
        "measured independently. This makes it straightforward to locate "
        "bottlenecks under load and to compare configurations objectively. "
    ) * 3,
    prompt_tokens=620,
    completion_tokens=210,
)
