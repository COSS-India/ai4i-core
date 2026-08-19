"""
Common response envelope for the unified inference endpoint.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ModelMetadata(BaseModel):
    """
    Model identity/provenance, resolved from mm_models via service_info.

    Surfaced so API/portal clients can echo modelProvider + modelVersion into
    the Feedback API without a second lookup (both are required there).
    Populated for the 10 Triton-backed task services; LLM and Pipeline don't
    go through this envelope so they never carry this block.
    """

    modelProvider: Optional[str] = Field(None, description="mm_models.submitter.name")
    modelVersion: Optional[str] = Field(None, description="mm_models.version")
    language: List[Dict[str, Any]] = Field(
        default_factory=list, description="mm_models.languages"
    )


class GenericInferenceResponse(BaseModel):
    """
    Unified inference response envelope.
    Output structure is task-specific and validated via task_type.
    """

    output: List[Dict[str, Any]] = Field(..., description="Task-specific output results")

    # Optional response metadata
    config: Optional[Dict[str, Any]] = Field(
        None, description="Response metadata from task service"
    )

    # Optional SMR routing metadata
    smr_response: Optional[Dict[str, Any]] = Field(
        None, description="SmartModelRouter routing metadata"
    )

    # Model identity metadata for the upcoming Feedback API (additive; absent
    # or null is backward-compatible with existing clients).
    model: Optional[ModelMetadata] = Field(
        None, description="Model identity metadata for feedback submission"
    )


# ── OpenAI-compatible chat response schema (routes/inference.py's /chat, /chat/completions) ──
#
# /chat and /chat/completions forward the request payload to an
# OpenAI-compatible upstream LLM verbatim — the route keeps a plain
# Dict[str, Any] body (see _CHAT_EXAMPLE there) rather than a Pydantic
# request model, so an upstream-supported field is never rejected here.
# This response schema is documentation only (wired via `responses=`, not
# `response_model=`), describing the non-streaming JSON shape for Swagger.


class ChatMessage(BaseModel):
    """One OpenAI chat message (request or response side)."""

    model_config = ConfigDict(extra="allow")

    role: str = Field(..., description="'system' | 'user' | 'assistant' | 'tool'.")
    content: Optional[Any] = Field(
        None, description="Message text, or a content-part list for multimodal input."
    )


class ChatChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: ChatMessage


class ChatUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response, forwarded verbatim from
    the upstream LLM. Documentation only — describes the non-streaming JSON
    shape; a request with ``stream: true`` instead returns a text/event-stream
    SSE body, which this schema does not (and cannot) describe."""

    model_config = ConfigDict(extra="allow", json_schema_extra={"example": {
        "model": "llm-service-1",
        "choices": [
            {"message": {"role": "assistant", "content": "Hello! How can I help you?"}}
        ],
        "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
    }})

    model: Optional[str] = None
    choices: List[ChatChoice] = Field(default_factory=list)
    usage: Optional[ChatUsage] = None
