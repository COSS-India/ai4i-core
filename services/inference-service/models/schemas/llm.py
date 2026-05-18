"""LLM (Large Language Model) service request/response schemas."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TextInput(BaseModel):
    """Input for LLM task."""

    source: str = Field(..., description="Input text for LLM processing")


class LLMConfig(BaseModel):
    """Configuration for LLM inference."""

    service_id: str = Field(..., description="Service ID (required)")
    temperature: Optional[float] = Field(0.7, description="Sampling temperature (0-2)")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    top_p: Optional[float] = Field(None, description="Top-P sampling parameter")
    top_k: Optional[int] = Field(None, description="Top-K sampling parameter")
    system_prompt: Optional[str] = Field(None, description="System prompt/instruction")


class LLMInferenceRequest(BaseModel):
    """Request for LLM inference."""

    input: List[TextInput] = Field(..., min_items=1, max_items=100, description="Input texts for LLM")
    config: LLMConfig = Field(..., description="LLM configuration")


class LLMOutput(BaseModel):
    """Output from LLM inference."""

    input_text: str = Field(..., description="Original input text")
    generated_text: str = Field(..., description="Generated text from LLM")
    tokens_used: Optional[int] = Field(None, description="Number of tokens used")


class LLMInferenceResponse(BaseModel):
    """Response from LLM inference."""

    output: List[LLMOutput] = Field(..., description="LLM generation results")

    class Config:
        use_enum_values = True

    def dict(self, **kwargs):
        """Exclude None values from serialization."""
        return super().dict(exclude_none=True, **kwargs)
