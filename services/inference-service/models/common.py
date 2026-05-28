"""
Common request/response envelopes for unified inference endpoint.
Supports polymorphic input arrays (input, audio, image) and task-specific configs.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ControlConfig(BaseModel):
    """Optional control parameters for inference execution."""

    timeout_ms: Optional[int] = Field(None, description="Request timeout in milliseconds")
    priority: Optional[str] = Field(None, description="Execution priority level")
    cache_result: Optional[bool] = Field(None, description="Whether to cache the result")

    class Config:
        extra = "allow"


class GenericInferenceRequest(BaseModel):
    """
    Unified inference request envelope supporting polymorphic input arrays.
    Task-specific configs use discriminated unions via task_type.
    """

    task_type: str = Field(..., description="Type of inference task (NMT, ASR, OCR, etc.)")

    # Polymorphic input arrays - only one should be populated based on task_type
    input: Optional[List[Dict[str, Any]]] = Field(
        None, description="Input data for text-based tasks"
    )
    audio: Optional[List[Dict[str, Any]]] = Field(
        None, description="Input data for audio-based tasks"
    )
    image: Optional[List[Dict[str, Any]]] = Field(
        None, description="Input data for image-based tasks"
    )

    # Task-specific config - validated against task_type
    config: Dict[str, Any] = Field(..., description="Task-specific configuration")

    # Optional control parameters
    control_config: Optional[ControlConfig] = Field(None, description="Control parameters")

    class Config:
        use_enum_values = True

    def get_input_data(self) -> List[Dict[str, Any]]:
        """Get the populated input array based on task type."""
        if self.input is not None:
            return self.input
        elif self.audio is not None:
            return self.audio
        elif self.image is not None:
            return self.image
        else:
            raise ValueError("No input data provided (input, audio, or image)")


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

    # Optional SMR response (only populated if service routing was resolved via SMR)
    smr_response: Optional[Dict[str, Any]] = Field(
        None, description="Smart Model Router metadata (if routing was performed)"
    )

    class Config:
        use_enum_values = True

class NMTInferenceResponse(BaseModel):
    """NMT-specific response envelope: output array + SMR metadata only."""

    output: List[Dict[str, Any]] = Field(..., description="Translation output results")
    smr_response: Optional[Dict[str, Any]] = Field(
        None, description="Smart Model Router metadata (if routing was performed)"
    )

    class Config:
        use_enum_values = True


