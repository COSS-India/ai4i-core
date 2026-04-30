"""
NER Response Models

Pydantic models for NER inference responses, mirroring the style used
by other services while keeping a ULCA-like structure.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    NER = "ner"


class NerTokenPrediction(BaseModel):
    """Token-level NER prediction."""

    token: Optional[str] = Field(None, description="Token text")
    tag: str = Field(..., description="NER tag (e.g., PERSON, ORG, O)")
    tokenIndex: Optional[int] = Field(
        None, description="Index of token within the input text"
    )
    tokenStartIndex: int = Field(
        ..., description="Character start index of token in the input text"
    )
    tokenEndIndex: int = Field(
        ..., description="Character end index of token in the input text"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class NerPrediction(BaseModel):
    """NER prediction for a single input text."""

    source: Optional[str] = Field(None, description="Original source text")
    nerPrediction: List[NerTokenPrediction] = Field(
        ..., description="List of token-level predictions"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)


class NerInferenceResponse(BaseModel):
    """Main NER inference response model."""

    taskType: TaskType = Field(
        default=TaskType.NER, description="Type of task (always 'ner')"
    )
    output: List[NerPrediction] = Field(
        ..., description="List of NER predictions (one per input text)"
    )
    config: Optional[Dict[str, Any]] = Field(
        None, description="Response configuration metadata (reserved for future use)"
    )

    def dict(self, **kwargs):  # type: ignore[override]
        """Override dict() to exclude None values."""
        return super().dict(exclude_none=True, **kwargs)



