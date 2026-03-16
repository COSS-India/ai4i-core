"""
Pydantic schemas for the Request Profiler API.

The internal API accepts only the `text` field.
The upstream profiler API options and source language are applied
as defaults inside the service layer so callers stay decoupled
from the upstream contract.
"""

from pydantic import BaseModel, Field


class ProfileRequest(BaseModel):
    """Incoming request schema for POST /api/v1/profile."""

    text: str = Field(
        ...,
        description="The text to profile for domain and complexity analysis.",
        examples=["The patient was administered 500mg of amoxicillin for bacterial infection treatment."],
    )
