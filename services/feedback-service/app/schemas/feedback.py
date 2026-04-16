"""
Pydantic schemas for the Feedback service.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Implicit telemetry event
# ---------------------------------------------------------------------------

class ImplicitEventRequest(BaseModel):
    trace_id: str
    service_id: str
    task_type: Literal["nmt", "asr", "tts", "ocr"]
    language: Optional[str] = None
    action: Literal["COPY_TRANSLATION", "COPY_SOURCE", "CLEAR_RESULTS", "RETRANSLATE", "CORRECTION", "ABANDON"]
    reward_score: float = Field(ge=-1.0, le=1.0)
    metrics: Optional[Dict[str, Any]] = None
    source_input: Optional[str] = None
    model_output: Optional[str] = None


# ---------------------------------------------------------------------------
# Explicit feedback submission
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    trace_id: str
    service_id: str
    task_type: Literal["nmt", "asr", "tts", "ocr"]
    language: Optional[str] = None
    source_input: str
    model_output: str
    feedback_source: Optional[Literal["user", "system", "batch"]] = "user"
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    trigger_evaluation: bool = False


class FeedbackResponse(BaseModel):
    id: UUID
    trace_id: str
    ai_status: str
    message: str


# ---------------------------------------------------------------------------
# Status query
# ---------------------------------------------------------------------------

class FeedbackStatusResponse(BaseModel):
    id: UUID
    organization: str
    tenant_id: Optional[str]
    trace_id: str
    service_id: str
    task_type: str
    language: Optional[str]
    source_input: str
    model_output: str
    human_correction: Optional[str]
    feedback_source: Optional[str]
    rating: Optional[int]
    implicit_score: Optional[int]
    event_log: Optional[List[Dict[str, Any]]]
    ai_status: str
    error_type: Optional[str]
    severity: Optional[str]
    payload: Optional[Dict[str, Any]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Human correction (golden data for RLHF)
# ---------------------------------------------------------------------------

class HumanCorrectionRequest(BaseModel):
    trace_id: str
    corrected_output: str


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

class BatchProcessRequest(BaseModel):
    """
    Admin-triggered batch evaluation pulled directly from the NMT database.

    The feedback service queries the NMT DB for the last `limit` completed
    translations and submits them to the LLM judge — no need to re-send
    source/translated text in the request body.
    """
    limit: int = Field(
        default=50, ge=1, le=500,
        description="Maximum number of NMT records to evaluate in this run.",
    )
    offset: int = Field(
        default=0, ge=0,
        description="Skip the first N records (for manual pagination across runs).",
    )
    skip_evaluated: bool = Field(
        default=True,
        description="Skip NMT records that already have a feedback_metrics entry.",
    )


class BatchProcessResponse(BaseModel):
    queued: int
    skipped: int
    message: str


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------

class OverridePassRequest(BaseModel):
    trace_id: str
    reason: Optional[str] = None
