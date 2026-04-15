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
    action: str                          # e.g. CORRECTION, RETRY, DWELL
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

class BatchItem(BaseModel):
    trace_id: str
    service_id: str
    task_type: Literal["nmt", "asr", "tts", "ocr"]
    language: Optional[str] = None
    source_input: str
    model_output: str


class BatchProcessRequest(BaseModel):
    items: List[BatchItem] = Field(min_length=1, max_length=100)


class BatchProcessResponse(BaseModel):
    queued: int
    message: str


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------

class OverridePassRequest(BaseModel):
    trace_id: str
    reason: Optional[str] = None
