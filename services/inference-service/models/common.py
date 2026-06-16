"""
Common response envelope for the unified inference endpoint.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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
