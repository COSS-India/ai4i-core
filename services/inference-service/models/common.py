"""
Common response envelope for the unified inference endpoint.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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
