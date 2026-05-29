"""Schemas for the /redact endpoint — request, response, and detected entity."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RedactionRequest(BaseModel):
    text: str = Field(..., max_length=20_000, description="Text to scan and redact.")


class DetectedEntity(BaseModel):
    entity_type:      str
    start_index:      int
    end_index:        int
    text_segment:     str
    detection_source: str
    risk_score:       float = 0.0


class RedactionMetadata(BaseModel):
    processing_time_ms: int
    language:           str
    domain:             str
    tenant_id:          str
    message:            Optional[str] = None


class RedactionResponse(BaseModel):
    redacted_text:  str
    pii_detected:   List[DetectedEntity]
    trace:          List[Dict[str, Any]]
    metadata:       RedactionMetadata
    original_text:  Optional[str] = None   # only when include_original_text=true
