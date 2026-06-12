"""
Common response envelope for the unified inference endpoint.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Single source of truth for the task types the inference service accepts.
# Imported by the Orchestrator (request validation) and the /inference/tasks
# route (capability listing) so the allowlist is declared once, not duplicated.
SUPPORTED_TASK_TYPES: tuple[str, ...] = (
    "NMT", "ASR", "OCR", "NER", "TTS", "PII", "LANGUAGE_DETECTION",
    "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION",
    "AUDIO_LANGUAGE_DETECTION",
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
