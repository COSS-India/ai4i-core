"""Stub responses for the LLM chat proxy.

Unlike the other modules in this package, these are NOT Triton KServe v2 shapes.
The LLM path (OpenAIProxyService.proxy) returns the upstream body verbatim, so
the stubs mirror an OpenAI-compatible chat-completion object: the route forwards
it unchanged and proxy_traced reads `usage` for the ai-inference token spans.

Three sizes based on the request prompt's character length:
  SMALL_LLM_RESPONSE   — short reply    (< 200 chars prompt)
  MEDIUM_LLM_RESPONSE  — a few sentences (200–999 chars prompt)
  LARGE_LLM_RESPONSE   — ~20k-token reply (>= 1000 chars prompt)

``chat_completion_chunks`` re-expresses any one of those bodies as the SSE
chunk sequence a vLLM-style server emits for the same reply, so the streaming
stub and the buffered stub are two views of one fixture and can never disagree
on the token counts that get billed.
"""

import re
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

_LARGE_PARAGRAPH = (
    "The proposed approach balances throughput and latency by batching "
    "requests where possible while keeping per-request overhead low. "
    "Each stage of the pipeline is instrumented so the time spent in "
    "validation, preprocessing, inference, and post-processing can be "
    "measured independently. This makes it straightforward to locate "
    "bottlenecks under load and to compare configurations objectively. "
)

# 317 reps plus this 20-word fragment tokenizes (tiktoken cl100k_base) to
# exactly 20000, so the declared completion_tokens below matches what the
# content actually tokenizes to instead of just being an asserted number.
_LARGE_PARAGRAPH_FRAGMENT = (
    "The proposed approach balances throughput and latency by batching "
    "requests where possible while keeping per-request overhead low. "
    "Each stage of "
)

LARGE_LLM_RESPONSE: dict[str, Any] = _completion(
    "Here is a detailed response. " + (_LARGE_PARAGRAPH * 317) + _LARGE_PARAGRAPH_FRAGMENT,
    prompt_tokens=620,
    completion_tokens=20000,
)


# One word per delta, which is roughly how a real vLLM server streams: one
# chunk per token. Keeping the chunk count proportional to the reply length is
# what makes the stubbed stream exercise a realistic number of per-chunk
# _record_stream_usage parses instead of collapsing the whole reply into one.
_WORDS_PER_DELTA = 1


def _content_deltas(text: str, words_per_delta: int = _WORDS_PER_DELTA) -> list[str]:
    """Slice ``text`` into per-delta pieces of ``words_per_delta`` words each.

    Cuts by offset at word boundaries rather than splitting and re-joining, so
    concatenating the pieces reproduces ``text`` exactly — whitespace included.
    A client that accumulates the deltas therefore ends up with the same string
    the buffered stub would have returned in one shot.
    """
    if not text:
        return []
    starts = [m.start() for m in re.finditer(r"\S+", text)]
    if not starts:
        return [text]
    pieces = []
    previous = 0
    for cut in starts[words_per_delta::words_per_delta]:
        pieces.append(text[previous:cut])
        previous = cut
    pieces.append(text[previous:])
    return pieces


def chat_completion_chunks(completion: dict[str, Any]) -> list[dict[str, Any]]:
    """Re-express a buffered chat-completion body as its SSE chunk sequence.

    Emits, in OpenAI streaming order: an opening role delta, one delta per
    ``_WORDS_PER_DELTA`` words of content, a ``finish_reason`` chunk, and
    finally a chunk carrying the completion's own ``usage`` block.

    That last chunk is not optional. OpenAIProxyService._record_stream_usage
    reads the token counts off it onto the ai-inference span, and the PPU Kafka
    consumer skips billing entirely when those come through as zero, so a
    stream without it would return 200 and silently bill nothing.

    Every dict is freshly built, so callers cannot mutate the shared fixtures
    and no deep copy is needed on the way out.
    """
    envelope = {
        "id": completion["id"],
        "object": "chat.completion.chunk",
        "created": completion["created"],
        "model": completion["model"],
    }
    chunks: list[dict[str, Any]] = [
        {**envelope, "choices": [
            {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
        ]},
    ]
    content = completion["choices"][0]["message"]["content"]
    chunks.extend(
        {**envelope, "choices": [
            {"index": 0, "delta": {"content": piece}, "finish_reason": None},
        ]}
        for piece in _content_deltas(content)
    )
    chunks.append(
        {**envelope, "choices": [
            {"index": 0, "delta": {}, "finish_reason": "stop"},
        ]},
    )
    # Usage rides a chunk with no choices, the way vLLM emits it when the
    # client asked for stream_options.include_usage (which
    # OpenAIProxyService._with_include_usage always does).
    chunks.append({**envelope, "choices": [], "usage": dict(completion["usage"])})
    return chunks
