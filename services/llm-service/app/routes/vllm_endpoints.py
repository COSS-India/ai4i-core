"""
OpenAI-compatible inference endpoints (dummy implementations).

Routes scaffolded so observability can be validated against the intended
response shape before vLLM is wired up. Spec contract:

  POST /chat/completion  →  maps to OpenAI's /v1/chat/completions
  POST /generate         →  maps to OpenAI's /v1/completions

Request and response bodies follow the OpenAI standard exactly. Each
response carries the canonical `usage` block:

    {
      "id": "...",
      "model": "...",
      "choices": [...],
      "usage": {
        "prompt_tokens":     <int>,
        "completion_tokens": <int>,
        "total_tokens":      <int>
      }
    }

ObservabilityMiddleware reads `usage` and `model` from the response body
and emits the `telemetry_obsv_llm_tokens_processed` histogram, with the
model name doubling as the `service_id` label (these endpoints do not
pass through model-management — that's why this router does NOT apply
`enforce_tenant_and_service_checks`).

The vLLM swap is a body-only change in each handler — the TODO(vllm-swap)
markers indicate exactly which lines move.

────────────────────────────────────────────────────────────────────────
TESTING THE DUMMIES (replace BASE_URL + API_KEY for your environment)

  curl -s -X POST $BASE_URL/chat/completion \
    -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
    -d '{
      "model": "dummy-llm-7b",
      "messages": [
        {"role":"system","content":"You are helpful."},
        {"role":"user","content":"What is the capital of France?"}
      ],
      "temperature": 0.7
    }'

  curl -s -X POST $BASE_URL/generate \
    -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
    -d '{ "model":"dummy-llm-7b", "prompt":"List three uses for baking soda:\n1.", "max_tokens":60 }'

After hitting either endpoint, check Prometheus for:
  telemetry_obsv_llm_tokens_processed_count{endpoint=~"/chat/completion|/generate"}
  histogram_quantile(0.5, sum by (le)(rate(
    telemetry_obsv_llm_tokens_processed_bucket{token_type="total"}[5m])))
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.dependencies.auth import AuthProvider

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["LLM Inference (OpenAI-compatible)"],
    dependencies=[Depends(AuthProvider)],
)


def _approx_token_count(text: str) -> int:
    """Rough 4-chars-per-token heuristic for dummy responses only.

    Real values from vLLM's tokenizer will replace this; the heuristic just
    makes the histogram bins vary with input size during testing.
    """
    return max(1, len(text or "") // 4)


def _flatten_message_content(content: Any) -> str:
    """OpenAI chat content is `string | [{type, text, ...}]`. Flatten to text
    so the dummy token estimator has something to measure."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
        return " ".join(parts)
    return ""


# ── /chat/completion ─────────────────────────────────────────────────

@router.post("/chat/completion")
async def chat_completion(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Dummy OpenAI-compatible /chat/completion endpoint.

    Body shape mirrors OpenAI's /v1/chat/completions exactly. Streaming
    (`stream: true`) is not implemented in the dummy — vLLM will provide it.
    """
    model = str(payload.get("model") or "dummy-llm-7b")
    messages = payload.get("messages") or []
    n = int(payload.get("n") or 1)

    prompt_text = " ".join(
        _flatten_message_content(m.get("content"))
        for m in messages
        if isinstance(m, dict)
    )

    # TODO(vllm-swap): replace this block with a vLLM client call —
    #   result = await vllm_client.chat_completions(payload); return result
    # vLLM already returns the OpenAI shape (id, object, created, model,
    # choices[*].message, usage). No further transformation needed.
    prompt_tokens = _approx_token_count(prompt_text)
    completion_tokens_per_choice = 50
    completion_text = (
        f"This is a dummy chat completion for model {model!r}. "
        f"It echoes that you sent {len(messages)} message(s)."
    )
    choices = [
        {
            "index": i,
            "message": {"role": "assistant", "content": completion_text},
            "finish_reason": "stop",
            "logprobs": None,
        }
        for i in range(n)
    ]
    completion_tokens = completion_tokens_per_choice * n

    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    logger.debug(
        "dummy chat_completion: model=%s prompt_tokens=%d completion_tokens=%d",
        model, prompt_tokens, completion_tokens,
    )
    return response


# ── /generate ────────────────────────────────────────────────────────

@router.post("/generate")
async def generate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Dummy OpenAI-compatible /generate endpoint (text completion).

    Per spec, `prompt` may be a single string or an array of strings (batch).
    Streaming is not implemented in the dummy.
    """
    model = str(payload.get("model") or "dummy-llm-7b")
    raw_prompt = payload.get("prompt") or ""
    n = int(payload.get("n") or 1)

    prompts: List[str] = (
        [str(p) for p in raw_prompt] if isinstance(raw_prompt, list) else [str(raw_prompt)]
    )

    # TODO(vllm-swap): replace with —
    #   result = await vllm_client.generate(payload); return result
    # vLLM's /generate returns the same OpenAI shape.
    prompt_tokens = sum(_approx_token_count(p) for p in prompts)
    completion_tokens_per_choice = 80
    completion_text = (
        f"This is a dummy generate response for model {model!r}. "
        f"Received {len(prompts)} prompt(s)."
    )
    choices = []
    for prompt_idx, _p in enumerate(prompts):
        for choice_idx in range(n):
            choices.append({
                "text": completion_text,
                "index": prompt_idx * n + choice_idx,
                "logprobs": None,
                "finish_reason": "stop",
            })
    completion_tokens = completion_tokens_per_choice * len(choices)

    response = {
        "id": f"cmpl-{uuid.uuid4().hex[:16]}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    logger.debug(
        "dummy generate: model=%s prompts=%d prompt_tokens=%d completion_tokens=%d",
        model, len(prompts), prompt_tokens, completion_tokens,
    )
    return response
